"""Validation and normalization of MQTT payloads."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from coldchain_guardian.contracts import (
    SCHEMA_VERSION,
    CommandMessage,
    DeviceStateMessage,
    SensorReading,
    TemperatureOverrideCommand,
    parse_timestamp,
)


class MessageValidationError(ValueError):
    """Raised when a received MQTT message violates its data contract."""


def _string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise MessageValidationError(f"{name} must be a non-empty string")
    return value


def _number(payload: Mapping[str, Any], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MessageValidationError(f"{name} must be numeric")
    return float(value)


def _common(payload: Mapping[str, Any], expected_shipment_id: str) -> tuple[str, str]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise MessageValidationError(
            f"schema_version must equal {SCHEMA_VERSION}"
        )
    shipment_id = _string(payload, "shipment_id")
    if shipment_id != expected_shipment_id:
        raise MessageValidationError("message belongs to a different shipment")
    timestamp = _string(payload, "timestamp")
    try:
        parse_timestamp(timestamp)
    except ValueError as exc:
        raise MessageValidationError(str(exc)) from exc
    return shipment_id, timestamp


def validate_sensor_reading(
    payload: Mapping[str, Any],
    *,
    expected_shipment_id: str,
    expected_sensor_type: str,
) -> SensorReading:
    shipment_id, timestamp = _common(payload, expected_shipment_id)
    device_id = _string(payload, "device_id")
    sensor_type = _string(payload, "sensor_type")
    if sensor_type != expected_sensor_type:
        raise MessageValidationError(
            f"sensor_type must equal {expected_sensor_type} for this topic"
        )
    value = _number(payload, "value")
    unit = _string(payload, "unit")

    if sensor_type == "temperature":
        if unit != "C":
            raise MessageValidationError("temperature unit must be C")
        if not -100.0 <= value <= 100.0:
            raise MessageValidationError("temperature is outside the accepted safety range")
    elif sensor_type == "humidity":
        if unit != "%":
            raise MessageValidationError("humidity unit must be %")
        if not 0.0 <= value <= 100.0:
            raise MessageValidationError("humidity must be between 0 and 100")
    else:
        raise MessageValidationError(f"unsupported sensor type: {sensor_type}")

    return SensorReading(
        device_id=device_id,
        shipment_id=shipment_id,
        timestamp=timestamp,
        sensor_type=sensor_type,
        value=value,
        unit=unit,
    )


def validate_state_message(
    payload: Mapping[str, Any],
    *,
    expected_shipment_id: str,
    allowed_states: Collection[str],
    require_source: bool = False,
) -> DeviceStateMessage:
    shipment_id, timestamp = _common(payload, expected_shipment_id)
    device_id = _string(payload, "device_id")
    state = _string(payload, "state")
    if state not in allowed_states:
        expected = ", ".join(sorted(allowed_states))
        raise MessageValidationError(f"state must be one of: {expected}")

    source_value = payload.get("source")
    if require_source:
        source = _string(payload, "source")
    elif source_value is None:
        source = None
    elif isinstance(source_value, str) and source_value.strip():
        source = source_value
    else:
        raise MessageValidationError("source must be a non-empty string when supplied")

    return DeviceStateMessage(
        device_id=device_id,
        shipment_id=shipment_id,
        timestamp=timestamp,
        state=state,
        source=source,
    )


def validate_command_message(
    payload: Mapping[str, Any],
    *,
    expected_shipment_id: str,
    allowed_commands: Collection[str],
    allowed_sources: Collection[str],
) -> CommandMessage:
    shipment_id, timestamp = _common(payload, expected_shipment_id)
    command = _string(payload, "command")
    source = _string(payload, "source")
    if command not in allowed_commands:
        expected = ", ".join(sorted(allowed_commands))
        raise MessageValidationError(f"command must be one of: {expected}")
    if source not in allowed_sources:
        expected = ", ".join(sorted(allowed_sources))
        raise MessageValidationError(f"source must be one of: {expected}")
    return CommandMessage(
        shipment_id=shipment_id,
        timestamp=timestamp,
        command=command,
        source=source,
    )


def validate_alert_ack(
    payload: Mapping[str, Any], *, expected_shipment_id: str
) -> int:
    _common(payload, expected_shipment_id)
    alert_id = payload.get("alert_id")
    if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id <= 0:
        raise MessageValidationError("alert_id must be a positive integer")
    return alert_id


def validate_temperature_override(
    payload: Mapping[str, Any],
    *,
    expected_shipment_id: str,
    minimum_c: float,
    maximum_c: float,
) -> TemperatureOverrideCommand:
    shipment_id, timestamp = _common(payload, expected_shipment_id)
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise MessageValidationError("enabled must be a boolean")
    source = _string(payload, "source")
    if source != "KNOB":
        raise MessageValidationError("temperature override source must be KNOB")

    target_value = payload.get("target_temperature_c")
    if enabled:
        target = _number(payload, "target_temperature_c")
        if not minimum_c <= target <= maximum_c:
            raise MessageValidationError(
                f"override target must be between {minimum_c} and {maximum_c}"
            )
    elif target_value is None:
        target = None
    elif isinstance(target_value, bool) or not isinstance(target_value, (int, float)):
        raise MessageValidationError(
            "target_temperature_c must be numeric or null"
        )
    else:
        target = float(target_value)

    return TemperatureOverrideCommand(
        shipment_id=shipment_id,
        timestamp=timestamp,
        enabled=enabled,
        target_temperature_c=target,
        source=source,
    )
