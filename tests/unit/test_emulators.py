from __future__ import annotations

import json
import unittest

from coldchain_guardian.config import load_config
from coldchain_guardian.contracts import (
    CommandMessage,
    CommandSource,
    RelayState,
    TemperatureOverrideCommand,
    encode_payload,
)
from coldchain_guardian.emulators.cooling_relay import CoolingRelayEmulator
from coldchain_guardian.emulators.dht import DhtEmulator
from coldchain_guardian.emulators.door_button import DoorButtonEmulator
from coldchain_guardian.emulators.temperature_knob import TemperatureKnobEmulator
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
        encoded = encode_payload(payload)
        self.publications.append((topic, json.loads(encoded), qos, retain))
        return True


class EmulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.topics = TopicRegistry(self.config.shipment.id)

    def test_dht_is_the_only_temperature_reading_publisher(self) -> None:
        dht_mqtt = FakeManagedClient()
        knob_mqtt = FakeManagedClient()
        dht = DhtEmulator(self.config, mqtt_client=dht_mqtt, random_seed=1)
        knob = TemperatureKnobEmulator(self.config, mqtt_client=knob_mqtt)

        knob.set_temperature(9.0)
        override_payload = knob_mqtt.publications[-1][1]
        dht._on_message(
            self.topics.dht_override_set,
            json.dumps(override_payload).encode(),
        )

        knob_topics = {item[0] for item in knob_mqtt.publications}
        temperature_messages = [
            item for item in dht_mqtt.publications if item[0] == self.topics.temperature
        ]
        self.assertNotIn(self.topics.temperature, knob_topics)
        self.assertEqual(temperature_messages[-1][1]["value"], 9.0)

    def test_door_toggle_publishes_retained_state(self) -> None:
        mqtt = FakeManagedClient()
        door = DoorButtonEmulator(self.config, mqtt_client=mqtt)

        state = door.toggle()

        self.assertEqual(str(state), "OPEN")
        self.assertEqual(mqtt.publications[-1][0], self.topics.door)
        self.assertEqual(mqtt.publications[-1][1]["state"], "OPEN")
        self.assertTrue(mqtt.publications[-1][3])

    def test_knob_release_disables_override(self) -> None:
        mqtt = FakeManagedClient()
        knob = TemperatureKnobEmulator(self.config, mqtt_client=mqtt)

        knob.release_override()

        payload = mqtt.publications[-1][1]
        self.assertFalse(payload["enabled"])
        self.assertIsNone(payload["target_temperature_c"])

    def test_relay_changes_only_after_mqtt_command(self) -> None:
        mqtt = FakeManagedClient()
        relay = CoolingRelayEmulator(self.config, mqtt_client=mqtt)
        command = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command=RelayState.ON,
            source=CommandSource.AUTO,
        )

        self.assertEqual(relay.state, RelayState.OFF)
        relay._on_message(self.topics.cooling_set, encode_payload(command))

        self.assertEqual(relay.state, RelayState.ON)
        self.assertEqual(mqtt.publications[-1][0], self.topics.cooling_status)
        self.assertEqual(mqtt.publications[-1][1]["source"], "AUTO")

    def test_reset_message_returns_relay_to_off(self) -> None:
        mqtt = FakeManagedClient()
        relay = CoolingRelayEmulator(self.config, mqtt_client=mqtt)
        relay._apply_command(RelayState.ON, CommandSource.MANUAL)
        reset = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command="RESET",
            source=CommandSource.RESET,
        )

        relay._on_message(self.topics.demo_reset_set, encode_payload(reset))

        self.assertEqual(relay.state, RelayState.OFF)
        self.assertEqual(mqtt.publications[-1][1]["source"], "RESET")


if __name__ == "__main__":
    unittest.main()

