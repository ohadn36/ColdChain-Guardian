"""Typed JSON payload contracts shared by all system components."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Any, Mapping


SCHEMA_VERSION = 1


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ALARM = "ALARM"


class DoorState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class RelayState(StrEnum):
    ON = "ON"
    OFF = "OFF"


class ControlMode(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class CommandSource(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    RESET = "RESET"


def now_iso() -> str:
    """Return a timezone-aware ISO 8601 timestamp with millisecond precision."""

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO 8601 timestamp and require timezone information."""

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("timestamp must be valid ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def encode_payload(message: Mapping[str, Any] | object) -> bytes:
    """Serialize a mapping or dataclass as compact UTF-8 JSON."""

    payload = asdict(message) if hasattr(message, "__dataclass_fields__") else message
    if not isinstance(payload, Mapping):
        raise TypeError("MQTT payload must be a mapping or dataclass")
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decode_payload(raw: bytes | str) -> dict[str, Any]:
    """Decode a UTF-8 JSON object."""

    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("payload must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("payload root must be a JSON object")
    return value


@dataclass(frozen=True)
class SensorReading:
    device_id: str
    shipment_id: str
    timestamp: str
    sensor_type: str
    value: float
    unit: str
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        device_id: str,
        shipment_id: str,
        sensor_type: str,
        value: float,
        unit: str,
    ) -> SensorReading:
        return cls(
            device_id=device_id,
            shipment_id=shipment_id,
            timestamp=now_iso(),
            sensor_type=sensor_type,
            value=float(value),
            unit=unit,
        )


@dataclass(frozen=True)
class DeviceStateMessage:
    device_id: str
    shipment_id: str
    timestamp: str
    state: str
    source: str | None = None
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        device_id: str,
        shipment_id: str,
        state: StrEnum | str,
        source: StrEnum | str | None = None,
    ) -> DeviceStateMessage:
        return cls(
            device_id=device_id,
            shipment_id=shipment_id,
            timestamp=now_iso(),
            state=str(state),
            source=None if source is None else str(source),
        )


@dataclass(frozen=True)
class CommandMessage:
    shipment_id: str
    timestamp: str
    command: str
    source: str
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        shipment_id: str,
        command: StrEnum | str,
        source: StrEnum | str,
    ) -> CommandMessage:
        return cls(
            shipment_id=shipment_id,
            timestamp=now_iso(),
            command=str(command),
            source=str(source),
        )


@dataclass(frozen=True)
class AlertEvent:
    alert_id: int
    shipment_id: str
    timestamp: str
    severity: str
    alert_type: str
    message: str
    acknowledged: bool = False
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class TemperatureOverrideCommand:
    shipment_id: str
    timestamp: str
    enabled: bool
    target_temperature_c: float | None
    source: str = "KNOB"
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        shipment_id: str,
        enabled: bool,
        target_temperature_c: float | None,
    ) -> TemperatureOverrideCommand:
        if enabled and target_temperature_c is None:
            raise ValueError("enabled override requires a target temperature")
        return cls(
            shipment_id=shipment_id,
            timestamp=now_iso(),
            enabled=enabled,
            target_temperature_c=(
                None if target_temperature_c is None else float(target_temperature_c)
            ),
        )
