from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from coldchain_guardian.config import load_config
from coldchain_guardian.contracts import (
    CommandMessage,
    CommandSource,
    DeviceStateMessage,
    RelayState,
    SensorReading,
    encode_payload,
)
from coldchain_guardian.data_manager.manager import DataManager
from coldchain_guardian.database.db_manager import DatabaseManager
from coldchain_guardian.gui.models import DashboardSnapshot
from coldchain_guardian.topics import TopicRegistry


class FakeManagedClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.publications: list[tuple[str, dict, int, bool]] = []

    def start(self, **kwargs) -> bool:
        return True

    def stop(self) -> None:
        self.is_connected = False

    def publish(self, topic, payload, *, qos=1, retain=False) -> bool:
        self.publications.append(
            (topic, json.loads(encode_payload(payload)), qos, retain)
        )
        return True


class DataManagerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.config = load_config()
        self.topics = TopicRegistry(self.config.shipment.id)
        self.database = DatabaseManager(
            Path(self.temporary_directory.name) / "manager-test.db"
        )
        self.database.initialize()
        self.mqtt = FakeManagedClient()
        self.manager = DataManager(
            self.config,
            database=self.database,
            mqtt_client=self.mqtt,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _temperature(self, value: float) -> bytes:
        return encode_payload(
            SensorReading.create(
                device_id=self.config.devices.temperature_sensor_id,
                shipment_id=self.config.shipment.id,
                sensor_type="temperature",
                value=value,
                unit="C",
            )
        )

    def test_temperature_flows_to_database_alert_and_relay_command(self) -> None:
        self.manager.process_message(self.topics.temperature, self._temperature(9.0))

        readings = self.database.recent_readings(sensor_type="temperature")
        alerts = self.database.recent_alerts()
        publications = [item for item in self.mqtt.publications]

        self.assertEqual(readings[0].value, 9.0)
        self.assertEqual(alerts[0].alert_type, "HIGH_TEMPERATURE")
        self.assertTrue(
            any(
                topic == self.topics.cooling_set and payload["command"] == "ON"
                for topic, payload, _, _ in publications
            )
        )
        self.assertTrue(
            any(topic == self.topics.state_snapshot for topic, _, _, _ in publications)
        )
        snapshot_payload = next(
            payload
            for topic, payload, _, _ in reversed(publications)
            if topic == self.topics.state_snapshot
        )
        snapshot = DashboardSnapshot.from_payload(
            snapshot_payload,
            expected_shipment_id=self.config.shipment.id,
        )
        self.assertEqual(snapshot.temperature_c, 9.0)

    def test_duplicate_reading_does_not_flood_alerts_or_commands(self) -> None:
        self.manager.process_message(self.topics.temperature, self._temperature(9.0))
        self.manager.process_message(self.topics.temperature, self._temperature(9.0))

        high_alerts = [
            alert
            for alert in self.database.recent_alerts()
            if alert.alert_type == "HIGH_TEMPERATURE"
        ]
        on_commands = [
            payload
            for topic, payload, _, _ in self.mqtt.publications
            if topic == self.topics.cooling_set and payload["command"] == "ON"
        ]
        self.assertEqual(len(high_alerts), 1)
        self.assertEqual(len(on_commands), 1)

    def test_relay_status_is_confirmed_and_persisted(self) -> None:
        status = DeviceStateMessage.create(
            device_id=self.config.devices.cooling_relay_id,
            shipment_id=self.config.shipment.id,
            state=RelayState.ON,
            source=CommandSource.AUTO,
        )

        self.manager.process_message(self.topics.cooling_status, encode_payload(status))

        event = self.database.recent_actuator_events()[0]
        self.assertEqual(event.state, "ON")
        self.assertEqual(self.manager.rules.relay_state, RelayState.ON)
        self.assertEqual(self.database.recent_alerts()[0].alert_type, "COOLING_ON")

    def test_ack_is_persisted_and_republished(self) -> None:
        self.manager.process_message(self.topics.temperature, self._temperature(9.0))
        alert_id = self.database.recent_alerts()[0].id
        ack = {
            "schema_version": 1,
            "shipment_id": self.config.shipment.id,
            "timestamp": SensorReading.create(
                device_id="unused",
                shipment_id=self.config.shipment.id,
                sensor_type="temperature",
                value=5,
                unit="C",
            ).timestamp,
            "alert_id": alert_id,
        }

        self.manager.process_message(
            self.topics.alert_ack_set, json.dumps(ack).encode()
        )

        self.assertTrue(self.database.get_alert(alert_id).acknowledged)
        self.assertTrue(
            any(
                topic == self.topics.alert_events
                and payload["alert_id"] == alert_id
                and payload["acknowledged"]
                for topic, payload, _, _ in self.mqtt.publications
            )
        )

    def test_reset_preserves_history_and_waits_for_relay_confirmation(self) -> None:
        self.manager.process_message(self.topics.temperature, self._temperature(9.0))
        relay_on = DeviceStateMessage.create(
            device_id=self.config.devices.cooling_relay_id,
            shipment_id=self.config.shipment.id,
            state=RelayState.ON,
            source=CommandSource.AUTO,
        )
        self.manager.process_message(self.topics.cooling_status, encode_payload(relay_on))
        reset = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command="RESET",
            source=CommandSource.RESET,
        )

        self.manager.process_message(self.topics.demo_reset_set, encode_payload(reset))

        self.assertEqual(self.manager.rules.relay_state, RelayState.ON)
        self.assertIsNone(self.manager.rules.temperature)
        self.assertGreater(len(self.database.recent_readings()), 0)
        self.assertTrue(
            any(
                alert.alert_type == "DEMO_RESET"
                for alert in self.database.recent_alerts()
            )
        )


if __name__ == "__main__":
    unittest.main()
