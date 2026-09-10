from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    GUI_AVAILABLE = True
except ModuleNotFoundError:
    QApplication = None
    GUI_AVAILABLE = False


@unittest.skipUnless(GUI_AVAILABLE, "PySide6 is not installed")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_dashboard_renders_live_state_and_alert(self) -> None:
        from coldchain_guardian.config import load_config
        from coldchain_guardian.contracts import Severity, now_iso
        from coldchain_guardian.gui.dashboard import DashboardWidget
        from coldchain_guardian.gui.models import AlertView, DashboardSnapshot

        config = load_config()
        dashboard = DashboardWidget(config)
        dashboard.resize(1180, 760)
        snapshot = DashboardSnapshot.from_payload(
            {
                "schema_version": 1,
                "shipment_id": config.shipment.id,
                "timestamp": now_iso(),
                "temperature_c": 11.2,
                "temperature_status": "ALARM_HIGH",
                "humidity_percent": 45.6,
                "humidity_status": "NORMAL",
                "door_state": "OPEN",
                "cooling_state": "ON",
                "control_mode": "AUTO",
                "mqtt_connected": True,
                "database_online": True,
            },
            expected_shipment_id=config.shipment.id,
        )
        dashboard.update_snapshot(snapshot)
        dashboard.add_or_update_alert(
            AlertView(
                alert_id=1,
                timestamp=now_iso(),
                severity=Severity.ALARM,
                alert_type="CRITICAL_HIGH_TEMPERATURE",
                message="Critical high temperature: 11.2°C",
                acknowledged=False,
            )
        )
        dashboard.show()
        self.application.processEvents()

        self.assertEqual(dashboard.temperature_card.value_label.text(), "11.2 °C")
        self.assertEqual(dashboard.alert_table.rowCount(), 1)
        self.assertFalse(dashboard.cooling_on_button.isEnabled())
        self.assertGreater(dashboard.grab().width(), 0)
        dashboard.close()

    def test_status_cards_describe_state_without_repeating_it(self) -> None:
        from coldchain_guardian.config import load_config
        from coldchain_guardian.contracts import now_iso
        from coldchain_guardian.gui.dashboard import DashboardWidget
        from coldchain_guardian.gui.models import DashboardSnapshot

        config = load_config()
        dashboard = DashboardWidget(config)
        dashboard.update_snapshot(
            DashboardSnapshot.from_payload(
                {
                    "schema_version": 1,
                    "shipment_id": config.shipment.id,
                    "timestamp": now_iso(),
                    "temperature_c": 5.2,
                    "temperature_status": "NORMAL",
                    "humidity_percent": 45.0,
                    "humidity_status": "NORMAL",
                    "door_state": "OPEN",
                    "cooling_state": "ON",
                    "control_mode": "MANUAL",
                    "mqtt_connected": True,
                    "database_online": True,
                },
                expected_shipment_id=config.shipment.id,
            )
        )

        self.assertEqual(dashboard.door_card.value_label.text(), "OPEN")
        self.assertEqual(dashboard.door_card.badge_label.text(), "ATTENTION")
        self.assertEqual(dashboard.cooling_card.value_label.text(), "ON")
        self.assertEqual(dashboard.cooling_card.badge_label.text(), "ACTIVE")
        self.assertEqual(dashboard.cooling_card.detail_label.text(), "MANUAL control")
        self.assertTrue(dashboard.cooling_on_button.isEnabled())
        self.assertFalse(dashboard.acknowledge_button.isEnabled())
        dashboard.close()

    def test_alarm_banner_follows_unacknowledged_severity(self) -> None:
        from coldchain_guardian.config import load_config
        from coldchain_guardian.contracts import Severity, now_iso
        from coldchain_guardian.gui.dashboard import DashboardWidget
        from coldchain_guardian.gui.models import AlertView
        from coldchain_guardian.gui.theme import Tone

        def alert(
            alert_id: int,
            severity: Severity,
            message: str,
            *,
            acknowledged: bool = False,
        ) -> AlertView:
            return AlertView(
                alert_id=alert_id,
                timestamp=now_iso(),
                severity=severity,
                alert_type="TEST",
                message=message,
                acknowledged=acknowledged,
            )

        dashboard = DashboardWidget(load_config())
        banner = dashboard.banner

        # An unacknowledged INFO event is not worth a banner.
        dashboard.set_alerts([alert(1, Severity.INFO, "Shipment door opened")])
        self.assertEqual(banner.property("tone"), str(Tone.NORMAL))

        dashboard.add_or_update_alert(alert(2, Severity.WARNING, "Door Open Too Long"))
        self.assertEqual(banner.property("tone"), str(Tone.WARNING))

        dashboard.add_or_update_alert(
            alert(3, Severity.ALARM, "Possible Cooling System Failure")
        )
        self.assertEqual(banner.property("tone"), str(Tone.ALARM))
        self.assertEqual(
            banner.headline_label.text(), "Possible Cooling System Failure"
        )

        for acknowledged in (
            alert(2, Severity.WARNING, "Door Open Too Long", acknowledged=True),
            alert(
                3,
                Severity.ALARM,
                "Possible Cooling System Failure",
                acknowledged=True,
            ),
        ):
            dashboard.add_or_update_alert(acknowledged)
        self.assertEqual(banner.property("tone"), str(Tone.NORMAL))
        dashboard.close()

    def test_history_loads_all_three_database_tables(self) -> None:
        from coldchain_guardian.contracts import (
            CommandSource,
            RelayState,
            SensorReading,
            Severity,
        )
        from coldchain_guardian.database.db_manager import (
            DatabaseManager,
            make_actuator_event,
        )
        from coldchain_guardian.gui.history import HistoryWidget

        with TemporaryDirectory() as directory:
            database = DatabaseManager(Path(directory) / "history.db")
            database.initialize()
            database.insert_reading(
                SensorReading.create(
                    device_id="temp_sensor_01",
                    shipment_id="shipment01",
                    sensor_type="temperature",
                    value=5.0,
                    unit="C",
                )
            )
            database.insert_alert(
                shipment_id="shipment01",
                severity=Severity.INFO,
                alert_type="TEST",
                message="History test",
            )
            database.insert_actuator_event(
                make_actuator_event(
                    device_id="cooling_relay_01",
                    shipment_id="shipment01",
                    state=RelayState.ON,
                    source=CommandSource.MANUAL,
                )
            )

            history = HistoryWidget(database, row_limit=10)
            history.show()
            self.application.processEvents()

            self.assertEqual(history.readings_table.rowCount(), 1)
            self.assertEqual(history.alerts_table.rowCount(), 1)
            self.assertEqual(history.actuators_table.rowCount(), 1)
            history.close()


if __name__ == "__main__":
    unittest.main()

