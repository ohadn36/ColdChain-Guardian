from __future__ import annotations

import unittest

from coldchain_guardian.contracts import SensorReading
from coldchain_guardian.data_manager.validator import (
    MessageValidationError,
    validate_alert_ack,
    validate_sensor_reading,
    validate_temperature_override,
)


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        reading = SensorReading.create(
            device_id="temp_sensor_01",
            shipment_id="shipment01",
            sensor_type="temperature",
            value=5.4,
            unit="C",
        )
        self.payload = {
            "schema_version": reading.schema_version,
            "device_id": reading.device_id,
            "shipment_id": reading.shipment_id,
            "timestamp": reading.timestamp,
            "sensor_type": reading.sensor_type,
            "value": reading.value,
            "unit": reading.unit,
        }

    def test_valid_temperature_reading(self) -> None:
        result = validate_sensor_reading(
            self.payload,
            expected_shipment_id="shipment01",
            expected_sensor_type="temperature",
        )
        self.assertEqual(result.value, 5.4)

    def test_rejects_wrong_shipment(self) -> None:
        self.payload["shipment_id"] = "shipment02"
        with self.assertRaisesRegex(MessageValidationError, "different shipment"):
            validate_sensor_reading(
                self.payload,
                expected_shipment_id="shipment01",
                expected_sensor_type="temperature",
            )

    def test_rejects_boolean_as_numeric_value(self) -> None:
        self.payload["value"] = True
        with self.assertRaisesRegex(MessageValidationError, "numeric"):
            validate_sensor_reading(
                self.payload,
                expected_shipment_id="shipment01",
                expected_sensor_type="temperature",
            )

    def test_ack_id_must_be_positive_integer(self) -> None:
        ack = {
            "schema_version": self.payload["schema_version"],
            "shipment_id": self.payload["shipment_id"],
            "timestamp": self.payload["timestamp"],
            "alert_id": 0,
        }
        with self.assertRaisesRegex(MessageValidationError, "positive integer"):
            validate_alert_ack(ack, expected_shipment_id="shipment01")

    def test_temperature_override_is_bounded(self) -> None:
        override = {
            "schema_version": self.payload["schema_version"],
            "shipment_id": self.payload["shipment_id"],
            "timestamp": self.payload["timestamp"],
            "enabled": True,
            "target_temperature_c": 25.0,
            "source": "KNOB",
        }
        with self.assertRaisesRegex(MessageValidationError, "between"):
            validate_temperature_override(
                override,
                expected_shipment_id="shipment01",
                minimum_c=-5.0,
                maximum_c=20.0,
            )


if __name__ == "__main__":
    unittest.main()
