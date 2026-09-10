# MQTT Topics and JSON Contracts

Base topic: `coldchain/shipment01`

## Topic registry

| Topic suffix | Publisher | Subscriber | QoS | Retained |
| --- | --- | --- | ---: | --- |
| `/sensors/temperature` | DHT | Data Manager | 0 | No |
| `/sensors/humidity` | DHT | Data Manager | 0 | No |
| `/sensors/door` | Door Button | Data Manager | 1 | Yes |
| `/emulators/dht/override/set` | Temperature Knob | DHT | 1 | No |
| `/emulators/dht/override/status` | DHT | Emulator Console | 1 | Yes |
| `/actuators/cooling/set` | Data Manager / GUI | Relay | 1 | No |
| `/actuators/cooling/status` | Relay | Data Manager | 1 | Yes |
| `/control/mode/set` | GUI | Data Manager | 1 | No |
| `/state/snapshot` | Data Manager | GUI | 1 | Yes |
| `/alerts/events` | Data Manager | GUI | 1 | No |
| `/alerts/ack/set` | GUI | Data Manager | 1 | No |
| `/demo/reset/set` | GUI / Console | Manager and emulators | 1 | No |

## Sensor reading

```json
{
  "schema_version": 1,
  "device_id": "temp_sensor_01",
  "shipment_id": "shipment01",
  "timestamp": "2026-09-09T21:30:00.000+03:00",
  "sensor_type": "temperature",
  "value": 5.4,
  "unit": "C"
}
```

Humidity uses `sensor_type: humidity` and `unit: %`.

## Door or relay state

```json
{
  "schema_version": 1,
  "device_id": "cooling_relay_01",
  "shipment_id": "shipment01",
  "timestamp": "2026-09-09T21:30:08.000+03:00",
  "state": "ON",
  "source": "AUTO"
}
```

The relay source is one of `AUTO`, `MANUAL`, or `RESET`. Door states do not require a source.

## Command

```json
{
  "schema_version": 1,
  "shipment_id": "shipment01",
  "timestamp": "2026-09-09T21:30:07.000+03:00",
  "command": "ON",
  "source": "AUTO"
}
```

## Temperature override

```json
{
  "schema_version": 1,
  "shipment_id": "shipment01",
  "timestamp": "2026-09-09T21:31:00.000+03:00",
  "enabled": true,
  "target_temperature_c": 9.0,
  "source": "KNOB"
}
```

The Knob never publishes to `/sensors/temperature`. It sends an override to the DHT, preserving one authoritative temperature publisher.

## State snapshot

```json
{
  "schema_version": 1,
  "shipment_id": "shipment01",
  "timestamp": "2026-09-09T21:31:02.000+03:00",
  "temperature_c": 9.0,
  "temperature_status": "WARNING_HIGH",
  "humidity_percent": 45.0,
  "humidity_status": "NORMAL",
  "door_state": "OPEN",
  "door_open_too_long": true,
  "cooling_state": "ON",
  "cooling_failure": false,
  "control_mode": "AUTO",
  "mqtt_connected": true,
  "database_online": true
}
```

`door_open_too_long` and `cooling_failure` are the two rule conditions that have
no sensor of their own. The snapshot carries them because alerts are an
append-only log: it records that a condition *started*, never that it ended. The
GUI needs live state to stop showing a condition once it clears.

## Alert event

```json
{
  "schema_version": 1,
  "alert_id": 42,
  "shipment_id": "shipment01",
  "timestamp": "2026-09-09T21:31:02.000+03:00",
  "severity": "WARNING",
  "alert_type": "HIGH_TEMPERATURE",
  "message": "Temperature above configured range: 9.0°C",
  "acknowledged": false
}
```

## Validation rules

- Payload root must be a JSON object.
- `schema_version` must be `1`.
- `shipment_id` must match the configured shipment.
- Timestamps must be valid ISO 8601 and include timezone information.
- Boolean values are not accepted as numbers.
- Humidity must be 0–100%; temperature has a broad safety-validation range of -100–100°C.
- Device state and command values must belong to explicit allowlists.

