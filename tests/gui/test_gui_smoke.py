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

