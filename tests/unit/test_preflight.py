from __future__ import annotations

import unittest
from unittest.mock import patch

from coldchain_guardian.config import load_config
from coldchain_guardian.preflight import PreflightReport, broker_is_reachable


class PreflightTests(unittest.TestCase):
    def test_report_requires_dependencies_and_broker_path(self) -> None:
        ready = PreflightReport((), True, None)
        missing_dependency = PreflightReport(("paho-mqtt",), True, None)
        no_broker = PreflightReport((), False, None)

        self.assertTrue(ready.can_launch)
        self.assertFalse(missing_dependency.can_launch)
        self.assertFalse(no_broker.can_launch)

    def test_closed_local_port_is_not_reported_as_reachable(self) -> None:
        with patch("socket.create_connection", side_effect=OSError):
            self.assertFalse(broker_is_reachable("127.0.0.1", 1883))

    def test_default_configuration_uses_localhost(self) -> None:
        config = load_config()
        self.assertEqual(config.mqtt.host, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
