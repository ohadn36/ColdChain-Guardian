from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from coldchain_guardian.contracts import CommandSource, RelayState, SensorReading, Severity
from coldchain_guardian.database.db_manager import DatabaseManager, make_actuator_event


class DatabaseManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database = DatabaseManager(
            Path(self.temporary_directory.name) / "coldchain-test.db"
        )
        self.database.initialize()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_reading_insert_and_query(self) -> None:
        row_id = self.database.insert_reading(
            SensorReading.create(
                device_id="temp_sensor_01",
                shipment_id="shipment01",
                sensor_type="temperature",
                value=5.4,
                unit="C",
            )
        )

        records = self.database.recent_readings(sensor_type="temperature")

        self.assertEqual(row_id, 1)
        self.assertEqual(records[0].value, 5.4)

    def test_alert_insert_and_acknowledge(self) -> None:
        alert = self.database.insert_alert(
            shipment_id="shipment01",
            severity=Severity.WARNING,
            alert_type="HIGH_TEMPERATURE",
            message="Temperature above configured range",
        )

        changed = self.database.acknowledge_alert(alert.alert_id)
        record = self.database.recent_alerts()[0]

        self.assertTrue(changed)
        self.assertTrue(record.acknowledged)
        self.assertIsNotNone(record.acknowledged_at)
        self.assertEqual(self.database.get_alert(alert.alert_id), record)

    def test_actuator_event_insert_and_query(self) -> None:
        row_id = self.database.insert_actuator_event(
            make_actuator_event(
                device_id="cooling_relay_01",
                shipment_id="shipment01",
                state=RelayState.ON,
                source=CommandSource.AUTO,
            )
        )

        record = self.database.recent_actuator_events()[0]

        self.assertEqual(row_id, 1)
        self.assertEqual(record.state, "ON")
        self.assertEqual(record.source, "AUTO")


if __name__ == "__main__":
    unittest.main()
