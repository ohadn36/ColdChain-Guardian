from __future__ import annotations

import unittest

from coldchain_guardian.contracts import (
    SensorReading,
    decode_payload,
    encode_payload,
    parse_timestamp,
)


class ContractsTests(unittest.TestCase):
    def test_sensor_reading_round_trip(self) -> None:
        reading = SensorReading.create(
            device_id="temp_sensor_01",
            shipment_id="shipment01",
            sensor_type="temperature",
            value=5.4,
            unit="C",
        )

        decoded = decode_payload(encode_payload(reading))

        self.assertEqual(decoded["schema_version"], 1)
        self.assertEqual(decoded["value"], 5.4)
        self.assertIsNotNone(parse_timestamp(decoded["timestamp"]).tzinfo)

    def test_payload_root_must_be_an_object(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON object"):
            decode_payload(b"[1, 2, 3]")

    def test_timestamp_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_timestamp("2026-09-09T12:00:00")


if __name__ == "__main__":
    unittest.main()

