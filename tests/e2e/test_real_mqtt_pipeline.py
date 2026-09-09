from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
import socket
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest

from coldchain_guardian.config import load_config
from coldchain_guardian.contracts import (
    CommandMessage,
    CommandSource,
    ControlMode,
    DoorState,
    RelayState,
    now_iso,
)
from coldchain_guardian.data_manager.manager import DataManager
from coldchain_guardian.database.db_manager import DatabaseManager
from coldchain_guardian.emulators.cooling_relay import CoolingRelayEmulator
from coldchain_guardian.emulators.dht import DhtEmulator
from coldchain_guardian.emulators.door_button import DoorButtonEmulator
from coldchain_guardian.emulators.temperature_knob import TemperatureKnobEmulator
from coldchain_guardian.mqtt_client import ManagedMqttClient
from coldchain_guardian.preflight import broker_is_reachable
from coldchain_guardian.topics import TopicRegistry


RUN_REAL_MQTT = os.environ.get("COLDCHAIN_RUN_E2E") == "1"


@unittest.skipUnless(RUN_REAL_MQTT, "set COLDCHAIN_RUN_E2E=1 to use local Mosquitto")
class RealMqttPipelineTests(unittest.TestCase):
    def test_complete_sensor_alert_relay_ack_and_reset_flow(self) -> None:
        mosquitto = shutil.which("mosquitto")
        if mosquitto is None:
            self.skipTest("Mosquitto executable not found")

        with TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            port = _available_port()
            broker_config = temporary_root / "mosquitto.conf"
            broker_config.write_text(
                f"listener {port} 127.0.0.1\n"
                "allow_anonymous true\n"
                "persistence false\n"
                "log_dest stdout\n",
                encoding="utf-8",
            )
            broker = subprocess.Popen(
                [mosquitto, "-c", str(broker_config)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            components = []
            try:
                self.assertTrue(_wait(lambda: broker_is_reachable("127.0.0.1", port)))
                base = load_config()
                config = replace(
                    base,
                    mqtt=replace(base.mqtt, port=port),
                    emulation=replace(base.emulation, publish_interval_seconds=10.0),
                    rules=replace(base.rules, door_warning_after_seconds=1),
                    database=replace(
                        base.database, path=temporary_root / "coldchain.db"
                    ),
                    logging=replace(
                        base.logging,
                        data_manager_path=temporary_root / "data_manager.log",
                    ),
                )
                topics = TopicRegistry(config.shipment.id)
                database = DatabaseManager(config.database.path)
                manager = DataManager(config, database=database)
                dht = DhtEmulator(config, random_seed=1)
                door = DoorButtonEmulator(config)
                knob = TemperatureKnobEmulator(config)
                relay = CoolingRelayEmulator(config)
                driver = ManagedMqttClient(
                    client_id="coldchain-e2e-driver",
                    config=config.mqtt,
                )
                components = [manager, dht, door, knob, relay, driver]
                for component in components:
                    self.assertTrue(component.start() is not False)

                self.assertTrue(_wait(lambda: manager.rules.temperature is not None))
                initial_reading_count = len(database.recent_readings())

                knob.set_temperature(9.0)
                self.assertTrue(_wait(lambda: manager.rules.temperature == 9.0))
                self.assertTrue(_wait(lambda: relay.state == RelayState.ON))
                self.assertTrue(
                    _wait(
                        lambda: any(
                            alert.alert_type == "HIGH_TEMPERATURE"
                            for alert in database.recent_alerts()
                        )
                    )
                )

                knob.set_temperature(10.0)
                self.assertTrue(_wait(lambda: manager.rules.temperature == 10.0))
                knob.set_temperature(11.0)
                self.assertTrue(_wait(lambda: manager.rules.temperature == 11.0))
                self.assertTrue(
                    _wait(
                        lambda: any(
                            alert.alert_type == "POSSIBLE_COOLING_FAILURE"
                            for alert in database.recent_alerts()
                        )
                    )
                )

                door.set_state(DoorState.OPEN)
                self.assertTrue(
                    _wait(
                        lambda: any(
                            alert.alert_type == "DOOR_OPEN_TOO_LONG"
                            for alert in database.recent_alerts()
                        ),
                        timeout=3.0,
                    )
                )

                warning = next(
                    alert
                    for alert in database.recent_alerts()
                    if not alert.acknowledged
                )
                driver.publish(
                    topics.alert_ack_set,
                    {
                        "schema_version": 1,
                        "shipment_id": config.shipment.id,
                        "timestamp": now_iso(),
                        "alert_id": warning.id,
                    },
                    qos=1,
                )
                self.assertTrue(
                    _wait(lambda: bool(database.get_alert(warning.id).acknowledged))
                )

                driver.publish(
                    topics.control_mode_set,
                    CommandMessage.create(
                        shipment_id=config.shipment.id,
                        command=ControlMode.MANUAL,
                        source=CommandSource.MANUAL,
                    ),
                    qos=1,
                )
                self.assertTrue(_wait(lambda: manager.rules.mode == ControlMode.MANUAL))
                driver.publish(
                    topics.cooling_set,
                    CommandMessage.create(
                        shipment_id=config.shipment.id,
                        command=RelayState.OFF,
                        source=CommandSource.MANUAL,
                    ),
                    qos=1,
                )
                self.assertTrue(_wait(lambda: relay.state == RelayState.OFF))
                self.assertTrue(
                    _wait(
                        lambda: any(
                            event.state == "OFF" and event.source == "MANUAL"
                            for event in database.recent_actuator_events()
                        )
                    )
                )

                driver.publish(
                    topics.demo_reset_set,
                    CommandMessage.create(
                        shipment_id=config.shipment.id,
                        command="RESET",
                        source=CommandSource.RESET,
                    ),
                    qos=1,
                )
                self.assertTrue(_wait(lambda: manager.rules.mode == ControlMode.AUTO))
                self.assertTrue(_wait(lambda: manager.rules.door_state == DoorState.CLOSED))
                self.assertTrue(_wait(lambda: not dht.snapshot().override_enabled))
                dht.publish_once(advance=False)
                self.assertTrue(_wait(lambda: manager.rules.temperature is not None))
                self.assertAlmostEqual(manager.rules.temperature, 5.0, places=1)
                self.assertGreater(len(database.recent_readings()), initial_reading_count)
            finally:
                for component in reversed(components):
                    try:
                        component.stop()
                    except Exception:
                        pass
                if broker.poll() is None:
                    broker.terminate()
                    try:
                        broker.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        broker.kill()
                        broker.wait(timeout=2)


def _available_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _wait(predicate, *, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


if __name__ == "__main__":
    unittest.main()
