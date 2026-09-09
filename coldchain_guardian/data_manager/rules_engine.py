"""Deterministic rules and state transitions for ColdChain Guardian."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable

from coldchain_guardian.config import RulesConfig
from coldchain_guardian.contracts import (
    ControlMode,
    DoorState,
    RelayState,
    Severity,
)


class TemperatureStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    WARNING_LOW = "WARNING_LOW"
    WARNING_HIGH = "WARNING_HIGH"
    ALARM_HIGH = "ALARM_HIGH"


class HumidityStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    WARNING = "WARNING"


@dataclass(frozen=True)
class AlertCandidate:
    severity: Severity
    alert_type: str
    message: str


@dataclass(frozen=True)
class RuleEvaluation:
    alerts: tuple[AlertCandidate, ...] = ()
    requested_relay_state: RelayState | None = None


class RulesEngine:
    """Hold current state and evaluate each incoming observation exactly once."""

    def __init__(self, config: RulesConfig) -> None:
        self.config = config
        self.mode = ControlMode.AUTO
        self.temperature: float | None = None
        self.temperature_status = TemperatureStatus.UNKNOWN
        self.humidity: float | None = None
        self.humidity_status = HumidityStatus.UNKNOWN
        self.door_state = DoorState.CLOSED
        self.door_opened_at: datetime | None = None
        self._door_warning_emitted = False
        self.relay_state = RelayState.OFF
        self._failure_alarm_active = False
        self._temperature_history: deque[float] = deque(
            maxlen=config.failure_trend_readings
        )

    def process_temperature(self, value: float) -> RuleEvaluation:
        self.temperature = float(value)
        self._temperature_history.append(self.temperature)
        alerts: list[AlertCandidate] = []

        next_status = self._classify_temperature(self.temperature)
        if next_status != self.temperature_status:
            alert = self._temperature_transition_alert(next_status, self.temperature)
            if alert is not None:
                alerts.append(alert)
            self.temperature_status = next_status

        failure_detected = self._is_cooling_failure_trend()
        if failure_detected and not self._failure_alarm_active:
            alerts.append(
                AlertCandidate(
                    severity=Severity.ALARM,
                    alert_type="POSSIBLE_COOLING_FAILURE",
                    message="Possible Cooling System Failure",
                )
            )
        self._failure_alarm_active = failure_detected

        return RuleEvaluation(
            alerts=tuple(alerts),
            requested_relay_state=self._desired_automatic_relay_state(),
        )

    def process_humidity(self, value: float) -> RuleEvaluation:
        self.humidity = float(value)
        next_status = (
            HumidityStatus.NORMAL
            if self.config.humidity_min_percent
            <= self.humidity
            <= self.config.humidity_max_percent
            else HumidityStatus.WARNING
        )
        alert: AlertCandidate | None = None
        if next_status != self.humidity_status:
            if next_status == HumidityStatus.WARNING:
                alert = AlertCandidate(
                    severity=Severity.WARNING,
                    alert_type="HUMIDITY_OUT_OF_RANGE",
                    message=f"Humidity outside configured range: {self.humidity:.1f}%",
                )
            elif self.humidity_status == HumidityStatus.WARNING:
                alert = AlertCandidate(
                    severity=Severity.INFO,
                    alert_type="HUMIDITY_RECOVERED",
                    message=f"Humidity returned to normal: {self.humidity:.1f}%",
                )
            self.humidity_status = next_status
        return RuleEvaluation(alerts=() if alert is None else (alert,))

    def process_door(
        self, state: DoorState, *, observed_at: datetime | None = None
    ) -> RuleEvaluation:
        if state == self.door_state:
            return RuleEvaluation()

        event_time = _aware_datetime(observed_at)
        self.door_state = state
        self._door_warning_emitted = False
        if state == DoorState.OPEN:
            self.door_opened_at = event_time
            alert = AlertCandidate(
                severity=Severity.INFO,
                alert_type="DOOR_OPENED",
                message="Shipment door opened",
            )
        else:
            self.door_opened_at = None
            alert = AlertCandidate(
                severity=Severity.INFO,
                alert_type="DOOR_CLOSED",
                message="Shipment door closed",
            )
        return RuleEvaluation(alerts=(alert,))

    def poll_time_rules(
        self, *, observed_at: datetime | None = None
    ) -> RuleEvaluation:
        now = _aware_datetime(observed_at)
        if (
            self.door_state == DoorState.OPEN
            and self.door_opened_at is not None
            and not self._door_warning_emitted
            and (now - self.door_opened_at).total_seconds()
            >= self.config.door_warning_after_seconds
        ):
            self._door_warning_emitted = True
            return RuleEvaluation(
                alerts=(
                    AlertCandidate(
                        severity=Severity.WARNING,
                        alert_type="DOOR_OPEN_TOO_LONG",
                        message="Door Open Too Long",
                    ),
                )
            )
        return RuleEvaluation()

    def update_relay_state(self, state: RelayState) -> None:
        self.relay_state = state
        if state == RelayState.OFF:
            self._failure_alarm_active = False

    def set_mode(self, mode: ControlMode) -> RuleEvaluation:
        self.mode = mode
        return RuleEvaluation(
            requested_relay_state=self._desired_automatic_relay_state()
        )

    def reset(self) -> None:
        self.mode = ControlMode.AUTO
        self.temperature = None
        self.temperature_status = TemperatureStatus.UNKNOWN
        self.humidity = None
        self.humidity_status = HumidityStatus.UNKNOWN
        self.door_state = DoorState.CLOSED
        self.door_opened_at = None
        self._door_warning_emitted = False
        self.relay_state = RelayState.OFF
        self._failure_alarm_active = False
        self._temperature_history.clear()

    def _classify_temperature(self, value: float) -> TemperatureStatus:
        if value < self.config.temperature_min_c:
            return TemperatureStatus.WARNING_LOW
        if value <= self.config.temperature_warning_high_c:
            return TemperatureStatus.NORMAL
        if value <= self.config.temperature_alarm_high_c:
            return TemperatureStatus.WARNING_HIGH
        return TemperatureStatus.ALARM_HIGH

    def _temperature_transition_alert(
        self, status: TemperatureStatus, value: float
    ) -> AlertCandidate | None:
        if status == TemperatureStatus.NORMAL:
            if self.temperature_status in (
                TemperatureStatus.WARNING_LOW,
                TemperatureStatus.WARNING_HIGH,
                TemperatureStatus.ALARM_HIGH,
            ):
                return AlertCandidate(
                    severity=Severity.INFO,
                    alert_type="TEMPERATURE_RECOVERED",
                    message=f"Temperature returned to normal: {value:.1f}°C",
                )
            return None
        if status == TemperatureStatus.WARNING_LOW:
            return AlertCandidate(
                severity=Severity.WARNING,
                alert_type="LOW_TEMPERATURE",
                message=f"Temperature below configured range: {value:.1f}°C",
            )
        if status == TemperatureStatus.WARNING_HIGH:
            return AlertCandidate(
                severity=Severity.WARNING,
                alert_type="HIGH_TEMPERATURE",
                message=f"Temperature above configured range: {value:.1f}°C",
            )
        return AlertCandidate(
            severity=Severity.ALARM,
            alert_type="CRITICAL_HIGH_TEMPERATURE",
            message=f"Critical high temperature: {value:.1f}°C",
        )

    def _desired_automatic_relay_state(self) -> RelayState | None:
        if self.mode != ControlMode.AUTO or self.temperature is None:
            return None
        if (
            self.temperature > self.config.temperature_warning_high_c
            and self.relay_state != RelayState.ON
        ):
            return RelayState.ON
        if (
            self.temperature < self.config.cooling_off_below_c
            and self.relay_state != RelayState.OFF
        ):
            return RelayState.OFF
        return None

    def _is_cooling_failure_trend(self) -> bool:
        history: Iterable[float] = self._temperature_history
        values = tuple(history)
        return (
            self.relay_state == RelayState.ON
            and len(values) == self.config.failure_trend_readings
            and all(value > self.config.temperature_warning_high_c for value in values)
            and all(left < right for left, right in zip(values, values[1:]))
        )


def _aware_datetime(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise ValueError("rule timestamps must include timezone information")
    return result

