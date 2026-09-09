# System Architecture

## Design goals

ColdChain Guardian is intentionally small, deterministic, and local-first. Each component has one responsibility, and every state-changing interaction is observable through MQTT or SQLite.

## Runtime processes

| Process | Responsibility |
| --- | --- |
| Mosquitto | Local MQTT message broker |
| Data Manager | Validation, state, rules, persistence, alerts, and automatic commands |
| Emulator Console | Hosts four separately implemented IoT emulator types |
| Main GUI | Live monitoring, history, ACK, mode, and manual relay requests |

## Forward data flow

```text
DHT / Door Emulator
        ↓ JSON over MQTT
     Data Manager
        ↓ validation
     Current State
        ↓
     Rules Engine
      ↙       ↘
  SQLite    MQTT alerts/snapshot
                  ↓
               Main GUI
```

## Actuator command flow

```text
Rules Engine or Main GUI
          ↓ MQTT command
 Cooling Relay Emulator
          ↓ MQTT confirmed status
       Data Manager
          ↓             ↓
       SQLite       GUI snapshot
```

The confirmed relay status is authoritative. A published command does not directly mutate the state shown by the manager or GUI.

## Threading model

- Each Paho client owns its network-loop thread.
- The DHT emulator owns one periodic publishing thread.
- The Data Manager owns one timer thread for elapsed-time rules such as `Door Open Too Long`.
- Data Manager state transitions are protected by an `RLock`.
- SQLite operations use short-lived connections in WAL mode, preventing connection sharing across callback and GUI threads.
- MQTT callbacks enter the Qt GUI through signals, so widgets are only updated on the GUI thread.

## Reliability decisions

- Invalid messages are logged and rejected without terminating the subscriber.
- Operational thresholds are loaded and validated from YAML.
- Alerts are generated on state transitions, not on every repeated reading.
- Pending automatic relay commands are rate-limited and retried after five seconds if no status is confirmed.
- Retained MQTT messages are used for important states, never for commands.
- Reset restores operating state but never deletes audit history.
- The launcher terminates only processes that it created.

## Trust boundaries

The local broker is restricted to `127.0.0.1` by `config/mosquitto.conf`. The demonstration uses anonymous access because the broker is loopback-only and short-lived. The project is an educational simulator and does not claim production security or regulatory compliance.

