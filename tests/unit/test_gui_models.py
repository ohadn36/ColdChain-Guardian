from __future__ import annotations

import unittest

from coldchain_guardian.contracts import now_iso
from coldchain_guardian.gui.models import (
    AlertView,
    DashboardSnapshot,
    ViewModelError,
)


class GuiViewModelTests(unittest.TestCase):
    def test_dashboard_snapshot_is_normalized(self) -> None:
        snapshot = DashboardSnapshot.from_payload(
            {
                "schema_version": 1,
                "shipment_id": "shipment01",
                "timestamp": now_iso(),
                "temperature_c": 5.4,
                "temperature_status": "NORMAL",
                "humidity_percent": 45.0,
                "humidity_status": "NORMAL",
                "door_state": "CLOSED",
                "cooling_state": "OFF",
                "control_mode": "AUTO",
                "mqtt_connected": True,
                "database_online": True,
            },
            expected_shipment_id="shipment01",
        )

        self.assertEqual(snapshot.temperature_c, 5.4)
        self.assertEqual(str(snapshot.control_mode), "AUTO")

    def test_snapshot_rejects_invalid_boolean(self) -> None:
        with self.assertRaisesRegex(ViewModelError, "boolean"):
            DashboardSnapshot.from_payload(
                {
                    "schema_version": 1,
                    "shipment_id": "shipment01",
                    "timestamp": now_iso(),
                    "temperature_c": None,
                    "temperature_status": "UNKNOWN",
                    "humidity_percent": None,
                    "humidity_status": "UNKNOWN",
                    "door_state": "CLOSED",
                    "cooling_state": "OFF",
                    "control_mode": "AUTO",
                    "mqtt_connected": "yes",
                    "database_online": True,
                },
                expected_shipment_id="shipment01",
            )

    def test_alert_view_requires_known_severity(self) -> None:
        with self.assertRaisesRegex(ViewModelError, "severity"):
            AlertView.from_payload(
                {
                    "schema_version": 1,
                    "alert_id": 1,
                    "shipment_id": "shipment01",
                    "timestamp": now_iso(),
                    "severity": "NOTICE",
                    "alert_type": "TEST",
                    "message": "Test alert",
                    "acknowledged": False,
                },
                expected_shipment_id="shipment01",
            )


if __name__ == "__main__":
    unittest.main()

