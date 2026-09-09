PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    sensor_type TEXT NOT NULL CHECK (sensor_type IN ('temperature', 'humidity')),
    value REAL NOT NULL,
    unit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ALARM')),
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0, 1)),
    acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS actuator_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('ON', 'OFF')),
    source TEXT NOT NULL CHECK (source IN ('AUTO', 'MANUAL', 'RESET'))
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp
    ON sensor_readings(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_type_timestamp
    ON sensor_readings(sensor_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
    ON alerts(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged
    ON alerts(acknowledged, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_actuator_events_timestamp
    ON actuator_events(timestamp DESC);

