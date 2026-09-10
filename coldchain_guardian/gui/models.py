"""Dependency-free view models used to validate data before rendering it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from coldchain_guardian.contracts import (
    ControlMode,
    DoorState,
    RelayState,
    SCHEMA_VERSION,
    Severity,
    parse_timestamp,
)


class ViewModelError(ValueError):
    """Raised when normalized manager data is not safe to render."""


@dataclass(frozen=True)
class DashboardSnapshot:
    shipment_id: str
    timestamp: str
    temperature_c: float | None
    temperature_status: str
    humidity_percent: float | None
    humidity_status: str
    door_state: DoorState
    cooling_state: RelayState
    control_mode: ControlMode
    mqtt_connected: bool
    database_online: bool
    # Rule states that have no sensor of their own. Absent means "not active",
    # so a snapshot from an older manager still renders.
    door_open_too_long: bool = False
    cooling_failure: bool = False

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], *, expected_shipment_id: str
    ) -> DashboardSnapshot:
        _require_schema(payload)
        shipment_id = _string(payload, "shipment_id")
        if shipment_id != expected_shipment_id:
            raise ViewModelError("snapshot belongs to a different shipment")
        timestamp = _string(payload, "timestamp")
        try:
            parse_timestamp(timestamp)
        except ValueError as exc:
            raise ViewModelError(str(exc)) from exc

        return cls(
            shipment_id=shipment_id,
            timestamp=timestamp,
            temperature_c=_optional_number(payload, "temperature_c"),
            temperature_status=_string(payload, "temperature_status"),
            humidity_percent=_optional_number(payload, "humidity_percent"),
            humidity_status=_string(payload, "humidity_status"),
            door_state=_enum(payload, "door_state", DoorState),
            cooling_state=_enum(payload, "cooling_state", RelayState),
            control_mode=_enum(payload, "control_mode", ControlMode),
            mqtt_connected=_boolean(payload, "mqtt_connected"),
            database_online=_boolean(payload, "database_online"),
            door_open_too_long=_optional_boolean(
                payload, "door_open_too_long"
            ),
            cooling_failure=_optional_boolean(payload, "cooling_failure"),
        )


@dataclass(frozen=True)
class AlertView:
    alert_id: int
    timestamp: str
    severity: Severity
    alert_type: str
    message: str
    acknowledged: bool

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], *, expected_shipment_id: str
    ) -> AlertView:
        _require_schema(payload)
        if _string(payload, "shipment_id") != expected_shipment_id:
            raise ViewModelError("alert belongs to a different shipment")
        alert_id = payload.get("alert_id")
        if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id <= 0:
            raise ViewModelError("alert_id must be a positive integer")
        timestamp = _string(payload, "timestamp")
        try:
            parse_timestamp(timestamp)
        except ValueError as exc:
            raise ViewModelError(str(exc)) from exc
        return cls(
            alert_id=alert_id,
            timestamp=timestamp,
            severity=_enum(payload, "severity", Severity),
            alert_type=_string(payload, "alert_type"),
            message=_string(payload, "message"),
            acknowledged=_boolean(payload, "acknowledged"),
        )


def _require_schema(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ViewModelError(f"schema_version must equal {SCHEMA_VERSION}")


def _string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ViewModelError(f"{name} must be a non-empty string")
    return value


def _optional_number(payload: Mapping[str, Any], name: str) -> float | None:
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ViewModelError(f"{name} must be numeric or null")
    return float(value)


def _boolean(payload: Mapping[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise ViewModelError(f"{name} must be a boolean")
    return value


def _optional_boolean(payload: Mapping[str, Any], name: str) -> bool:
    if name not in payload:
        return False
    return _boolean(payload, name)


def _enum(payload: Mapping[str, Any], name: str, enum_type):
    value = _string(payload, name)
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ViewModelError(f"invalid {name}: {value}") from exc

