"""Thread-safe-by-design SQLite access for application processes.

Each public operation uses a short-lived connection. This keeps MQTT callback
threads and the GUI history reader from sharing connection objects while WAL mode
allows concurrent readers and a single writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from coldchain_guardian.contracts import (
    AlertEvent,
    CommandSource,
    DeviceStateMessage,
    SensorReading,
    Severity,
    now_iso,
)


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class ReadingRecord:
    id: int
    timestamp: str
    shipment_id: str
    device_id: str
    sensor_type: str
    value: float
    unit: str


@dataclass(frozen=True)
class AlertRecord:
    id: int
    timestamp: str
    shipment_id: str
    severity: str
    alert_type: str
    message: str
    acknowledged: bool
    acknowledged_at: str | None


@dataclass(frozen=True)
class ActuatorEventRecord:
    id: int
    timestamp: str
    shipment_id: str
    device_id: str
    state: str
    source: str


class DatabaseManager:
    """Own the schema and all persistence operations for one SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        """Create the database directory, schema, and indexes when absent."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as connection:
            connection.executescript(schema)

    def health_check(self) -> bool:
        try:
            with self._connect() as connection:
                result = connection.execute("SELECT 1").fetchone()
            return result is not None and result[0] == 1
        except sqlite3.Error:
            return False

    def insert_reading(self, reading: SensorReading) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sensor_readings
                    (timestamp, shipment_id, device_id, sensor_type, value, unit)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    reading.timestamp,
                    reading.shipment_id,
                    reading.device_id,
                    reading.sensor_type,
                    reading.value,
                    reading.unit,
                ),
            )
            return _required_row_id(cursor)

    def insert_alert(
        self,
        *,
        shipment_id: str,
        severity: Severity | str,
        alert_type: str,
        message: str,
        timestamp: str | None = None,
    ) -> AlertEvent:
        alert_timestamp = timestamp or now_iso()
        severity_value = str(severity)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alerts
                    (timestamp, shipment_id, severity, alert_type, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    alert_timestamp,
                    shipment_id,
                    severity_value,
                    alert_type,
                    message,
                ),
            )
            alert_id = _required_row_id(cursor)
        return AlertEvent(
            alert_id=alert_id,
            shipment_id=shipment_id,
            timestamp=alert_timestamp,
            severity=severity_value,
            alert_type=alert_type,
            message=message,
        )

    def insert_actuator_event(self, event: DeviceStateMessage) -> int:
        if event.source is None:
            raise ValueError("actuator event source is required")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO actuator_events
                    (timestamp, shipment_id, device_id, state, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.timestamp,
                    event.shipment_id,
                    event.device_id,
                    event.state,
                    event.source,
                ),
            )
            return _required_row_id(cursor)

    def acknowledge_alert(self, alert_id: int, *, timestamp: str | None = None) -> bool:
        acknowledged_at = timestamp or now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE alerts
                SET acknowledged = 1, acknowledged_at = ?
                WHERE id = ? AND acknowledged = 0
                """,
                (acknowledged_at, alert_id),
            )
            return cursor.rowcount == 1

    def recent_readings(
        self,
        *,
        limit: int = 200,
        sensor_type: str | None = None,
    ) -> list[ReadingRecord]:
        safe_limit = _validate_limit(limit)
        query = """
            SELECT id, timestamp, shipment_id, device_id, sensor_type, value, unit
            FROM sensor_readings
        """
        parameters: list[Any] = []
        if sensor_type is not None:
            query += " WHERE sensor_type = ?"
            parameters.append(sensor_type)
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        parameters.append(safe_limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ReadingRecord(**dict(row)) for row in rows]

    def recent_alerts(self, *, limit: int = 200) -> list[AlertRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, timestamp, shipment_id, severity, alert_type, message,
                       acknowledged, acknowledged_at
                FROM alerts
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (_validate_limit(limit),),
            ).fetchall()
        return [
            AlertRecord(
                id=row["id"],
                timestamp=row["timestamp"],
                shipment_id=row["shipment_id"],
                severity=row["severity"],
                alert_type=row["alert_type"],
                message=row["message"],
                acknowledged=bool(row["acknowledged"]),
                acknowledged_at=row["acknowledged_at"],
            )
            for row in rows
        ]

    def recent_actuator_events(
        self, *, limit: int = 200
    ) -> list[ActuatorEventRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, timestamp, shipment_id, device_id, state, source
                FROM actuator_events
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (_validate_limit(limit),),
            ).fetchall()
        return [ActuatorEventRecord(**dict(row)) for row in rows]


def _required_row_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite did not return an inserted row ID")
    return int(cursor.lastrowid)


def _validate_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    return limit


def make_actuator_event(
    *,
    device_id: str,
    shipment_id: str,
    state: str,
    source: CommandSource | str,
) -> DeviceStateMessage:
    """Create a correctly shaped actuator event for persistence."""

    return DeviceStateMessage.create(
        device_id=device_id,
        shipment_id=shipment_id,
        state=state,
        source=source,
    )

