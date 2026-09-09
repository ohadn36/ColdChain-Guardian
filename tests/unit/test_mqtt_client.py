from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from coldchain_guardian.config import load_config
from coldchain_guardian.mqtt_client import ManagedMqttClient


class FakePahoClient:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.subscriptions: list[tuple[str, int]] = []
        self.publications: list[tuple[str, bytes, int, bool]] = []
        self.connect_arguments = None

    def reconnect_delay_set(self, *, min_delay: int, max_delay: int) -> None:
        self.reconnect_delays = (min_delay, max_delay)

    def connect_async(self, host: str, port: int, keepalive: int) -> None:
        self.connect_arguments = (host, port, keepalive)

    def loop_start(self) -> None:
        self.on_connect(self, None, None, 0, None)

    def loop_stop(self) -> None:
        pass

    def disconnect(self) -> None:
        self.on_disconnect(self, None, None, 0, None)

    def subscribe(self, topic: str, *, qos: int) -> None:
        self.subscriptions.append((topic, qos))

    def publish(self, topic: str, *, payload: bytes, qos: int, retain: bool):
        self.publications.append((topic, payload, qos, retain))
        return SimpleNamespace(rc=0)


class ManagedMqttClientTests(unittest.TestCase):
    def test_connection_subscription_and_json_publish(self) -> None:
        fake = FakePahoClient("test-client")
        config = load_config().mqtt
        client = ManagedMqttClient(
            client_id="test-client",
            config=config,
            subscriptions=(("coldchain/shipment01/sensors/+", 1),),
            client_factory=lambda client_id: fake,
        )

        connected = client.start(wait_timeout=0.1)
        accepted = client.publish(
            "coldchain/shipment01/test",
            {"ok": True},
            qos=1,
            retain=True,
        )

        self.assertTrue(connected)
        self.assertTrue(accepted)
        self.assertEqual(fake.subscriptions, [("coldchain/shipment01/sensors/+", 1)])
        self.assertEqual(json.loads(fake.publications[0][1]), {"ok": True})
        self.assertEqual(fake.publications[0][2:], (1, True))

        client.stop()
        self.assertFalse(client.is_connected)


if __name__ == "__main__":
    unittest.main()

