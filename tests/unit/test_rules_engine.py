from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from coldchain_guardian.config import load_config
from coldchain_guardian.contracts import ControlMode, DoorState, RelayState, Severity
from coldchain_guardian.data_manager.rules_engine import (
    RulesEngine,
    TemperatureStatus,
)


class RulesEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_config().rules

    def test_temperature_boundaries(self) -> None:
        cases = (
            (1.9, TemperatureStatus.WARNING_LOW, Severity.WARNING),
            (2.0, TemperatureStatus.NORMAL, None),
            (8.0, TemperatureStatus.NORMAL, None),
            (8.1, TemperatureStatus.WARNING_HIGH, Severity.WARNING),
            (10.0, TemperatureStatus.WARNING_HIGH, Severity.WARNING),
            (10.1, TemperatureStatus.ALARM_HIGH, Severity.ALARM),
        )
        for value, expected_status, expected_severity in cases:
            with self.subTest(value=value):
                engine = RulesEngine(self.rules)
                result = engine.process_temperature(value)
                self.assertEqual(engine.temperature_status, expected_status)
                actual = result.alerts[0].severity if result.alerts else None
                self.assertEqual(actual, expected_severity)

    def test_auto_cooling_uses_hysteresis(self) -> None:
        engine = RulesEngine(self.rules)
        self.assertEqual(
            engine.process_temperature(9.0).requested_relay_state,
            RelayState.ON,
        )
        engine.update_relay_state(RelayState.ON)
        self.assertIsNone(engine.process_temperature(7.5).requested_relay_state)
        self.assertEqual(
            engine.process_temperature(6.9).requested_relay_state,
            RelayState.OFF,
        )

    def test_manual_mode_disables_automatic_commands(self) -> None:
        engine = RulesEngine(self.rules)
        engine.set_mode(ControlMode.MANUAL)
        self.assertIsNone(engine.process_temperature(11.0).requested_relay_state)

    def test_door_warning_is_emitted_once_after_timeout(self) -> None:
        engine = RulesEngine(self.rules)
        opened_at = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

        opened = engine.process_door(DoorState.OPEN, observed_at=opened_at)
        early = engine.poll_time_rules(observed_at=opened_at + timedelta(seconds=9))
        warning = engine.poll_time_rules(observed_at=opened_at + timedelta(seconds=10))
        duplicate = engine.poll_time_rules(observed_at=opened_at + timedelta(seconds=20))

        self.assertEqual(opened.alerts[0].alert_type, "DOOR_OPENED")
        self.assertFalse(early.alerts)
        self.assertEqual(warning.alerts[0].alert_type, "DOOR_OPEN_TOO_LONG")
        self.assertFalse(duplicate.alerts)

    def test_detects_and_deduplicates_cooling_failure(self) -> None:
        engine = RulesEngine(self.rules)
        engine.update_relay_state(RelayState.ON)

        engine.process_temperature(9.0)
        engine.process_temperature(10.0)
        third = engine.process_temperature(11.0)
        fourth = engine.process_temperature(12.0)

        third_types = {alert.alert_type for alert in third.alerts}
        fourth_types = {alert.alert_type for alert in fourth.alerts}
        self.assertIn("POSSIBLE_COOLING_FAILURE", third_types)
        self.assertNotIn("POSSIBLE_COOLING_FAILURE", fourth_types)


if __name__ == "__main__":
    unittest.main()

