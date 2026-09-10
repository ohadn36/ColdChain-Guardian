"""MQTT-to-database processing application for ColdChain Guardian."""

from __future__ import annotations

import logging
from pathlib import Path
import signal
from threading import Event, RLock, Thread
import time
from typing import Any

from coldchain_guardian.config import AppConfig, load_config
from coldchain_guardian.contracts import (
    AlertEvent,
    CommandMessage,
    CommandSource,
    ControlMode,
    DoorState,
    RelayState,
    Severity,
    decode_payload,
    now_iso,
    parse_timestamp,
)
from coldchain_guardian.data_manager.rules_engine import RuleEvaluation, RulesEngine
from coldchain_guardian.data_manager.validator import (
    MessageValidationError,
    validate_alert_ack,
    validate_command_message,
    validate_sensor_reading,
    validate_state_message,
)
from coldchain_guardian.database.db_manager import AlertRecord, DatabaseManager
from coldchain_guardian.mqtt_client import ManagedMqttClient
from coldchain_guardian.topics import TopicRegistry


class DataManager:
    """Validate, persist, evaluate, and republish all operational data."""

    COMMAND_RETRY_SECONDS = 5.0

    def __init__(
        self,
        config: AppConfig,
        *,
        database: DatabaseManager | None = None,
        mqtt_client: ManagedMqttClient | Any | None = None,
        rules_engine: RulesEngine | None = None,
    ) -> None:
        self.config = config
        self.topics = TopicRegistry(config.shipment.id)
        self.database = database or DatabaseManager(config.database.path)
        self.rules = rules_engine or RulesEngine(config.rules)
        self._logger = _configure_logger(config)
        self._lock = RLock()
        self._stop_event = Event()
        self._timer_thread: Thread | None = None
        self._pending_relay_state: RelayState | None = None
        self._pending_relay_at = 0.0
        self._mqtt = mqtt_client or ManagedMqttClient(
            client_id=f"coldchain-manager-{config.shipment.id}",
            config=config.mqtt,
            subscriptions=tuple(
                (topic, 1) for topic in self.topics.manager_subscriptions
            ),
            on_message=self._on_message,
            on_connection_change=self._on_connection_change,
            logger=self._logger,
        )

    @property
    def is_connected(self) -> bool:
        return bool(self._mqtt.is_connected)

    def start(self) -> bool:
        self.database.initialize()
        connected = self._mqtt.start()
        self._stop_event.clear()
        self._timer_thread = Thread(
            target=self._timer_loop,
            name="data-manager-rules-timer",
            daemon=True,
        )
        self._timer_thread.start()
        self._logger.info("Data Manager started")
        if connected:
            self.publish_snapshot()
        return connected

    def stop(self) -> None:
        self._stop_event.set()
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=2.0)
        self._mqtt.stop()
        self._logger.info("Data Manager stopped")

    def process_message(self, topic: str, raw_payload: bytes) -> None:
        """Public deterministic entry point used by MQTT and integration tests."""

        with self._lock:
            payload = decode_payload(raw_payload)
            if topic == self.topics.temperature:
                reading = validate_sensor_reading(
                    payload,
                    expected_shipment_id=self.config.shipment.id,
                    expected_sensor_type="temperature",
                )
                self.database.insert_reading(reading)
                evaluation = self.rules.process_temperature(reading.value)
                self._logger.info("Temperature reading: %.2f C", reading.value)
                self._handle_evaluation(evaluation)
            elif topic == self.topics.humidity:
                reading = validate_sensor_reading(
                    payload,
                    expected_shipment_id=self.config.shipment.id,
                    expected_sensor_type="humidity",
                )
                self.database.insert_reading(reading)
                evaluation = self.rules.process_humidity(reading.value)
                self._handle_evaluation(evaluation)
            elif topic == self.topics.door:
                message = validate_state_message(
                    payload,
                    expected_shipment_id=self.config.shipment.id,
                    allowed_states={DoorState.OPEN, DoorState.CLOSED},
                )
                evaluation = self.rules.process_door(
                    DoorState(message.state),
                    observed_at=parse_timestamp(message.timestamp),
                )
                self._handle_evaluation(evaluation)
            elif topic == self.topics.cooling_status:
                self._process_relay_status(payload)
            elif topic == self.topics.control_mode_set:
                self._process_mode_command(payload)
            elif topic == self.topics.alert_ack_set:
                self._process_ack(payload)
            elif topic == self.topics.demo_reset_set:
                self._process_reset(payload)
            else:
                self._logger.warning("Ignoring unknown topic: %s", topic)
                return
            self.publish_snapshot()

    def publish_snapshot(self) -> None:
        payload = {
            "schema_version": 1,
            "shipment_id": self.config.shipment.id,
            "timestamp": now_iso(),
            "temperature_c": self.rules.temperature,
            "temperature_status": str(self.rules.temperature_status),
            "humidity_percent": self.rules.humidity,
            "humidity_status": str(self.rules.humidity_status),
            "door_state": str(self.rules.door_state),
            "door_open_too_long": self.rules.door_open_too_long,
            "cooling_state": str(self.rules.relay_state),
            "cooling_failure": self.rules.cooling_failure_active,
            "control_mode": str(self.rules.mode),
            "mqtt_connected": self.is_connected,
            "database_online": self.database.health_check(),
        }
        self._mqtt.publish(self.topics.state_snapshot, payload, qos=1, retain=True)

    def _on_message(self, topic: str, raw_payload: bytes) -> None:
        try:
            self.process_message(topic, raw_payload)
        except (MessageValidationError, ValueError):
            self._logger.exception("Rejected message on topic %s", topic)
        except Exception:
            self._logger.exception("Failed to process message on topic %s", topic)

    def _on_connection_change(self, connected: bool) -> None:
        if connected:
            self._logger.info("MQTT connection restored")
            self.publish_snapshot()

    def _process_relay_status(self, payload: dict[str, Any]) -> None:
        message = validate_state_message(
            payload,
            expected_shipment_id=self.config.shipment.id,
            allowed_states={RelayState.ON, RelayState.OFF},
            require_source=True,
        )
        try:
            source = CommandSource(message.source)
        except ValueError as exc:
            raise MessageValidationError("invalid relay command source") from exc

        state = RelayState(message.state)
        previous_state = self.rules.relay_state
        self.rules.update_relay_state(state)
        self._pending_relay_state = None
        if state != previous_state:
            self.database.insert_actuator_event(message)
            self._create_alert(
                severity=Severity.INFO,
                alert_type=f"COOLING_{state}",
                message=f"Cooling turned {state} ({source})",
            )
            self._logger.info("Cooling status changed to %s (%s)", state, source)

    def _process_mode_command(self, payload: dict[str, Any]) -> None:
        command = validate_command_message(
            payload,
            expected_shipment_id=self.config.shipment.id,
            allowed_commands={ControlMode.AUTO, ControlMode.MANUAL},
            allowed_sources={CommandSource.MANUAL},
        )
        mode = ControlMode(command.command)
        changed = mode != self.rules.mode
        evaluation = self.rules.set_mode(mode)
        if changed:
            self._create_alert(
                severity=Severity.INFO,
                alert_type="CONTROL_MODE_CHANGED",
                message=f"Control mode changed to {mode}",
            )
        self._handle_evaluation(evaluation)

    def _process_ack(self, payload: dict[str, Any]) -> None:
        alert_id = validate_alert_ack(
            payload, expected_shipment_id=self.config.shipment.id
        )
        if self.database.acknowledge_alert(alert_id):
            record = self.database.get_alert(alert_id)
            if record is not None:
                self._publish_alert_record(record)
            self._logger.info("Alert %s acknowledged", alert_id)

    def _process_reset(self, payload: dict[str, Any]) -> None:
        validate_command_message(
            payload,
            expected_shipment_id=self.config.shipment.id,
            allowed_commands={"RESET"},
            allowed_sources={CommandSource.RESET},
        )
        confirmed_relay_state = self.rules.relay_state
        self.rules.reset()
        # Relay state changes only after the emulator confirms the MQTT command.
        self.rules.update_relay_state(confirmed_relay_state)
        self._pending_relay_state = None
        self._create_alert(
            severity=Severity.INFO,
            alert_type="DEMO_RESET",
            message="Demo state reset requested",
        )
        self._logger.info("Demo state reset")

    def _handle_evaluation(self, evaluation: RuleEvaluation) -> None:
        for alert in evaluation.alerts:
            self._create_alert(
                severity=alert.severity,
                alert_type=alert.alert_type,
                message=alert.message,
            )
        if evaluation.requested_relay_state is not None:
            self._request_relay_state(evaluation.requested_relay_state)

    def _create_alert(
        self,
        *,
        severity: Severity,
        alert_type: str,
        message: str,
    ) -> AlertEvent:
        event = self.database.insert_alert(
            shipment_id=self.config.shipment.id,
            severity=severity,
            alert_type=alert_type,
            message=message,
        )
        self._mqtt.publish(self.topics.alert_events, event, qos=1)
        self._logger.log(
            logging.ERROR if severity == Severity.ALARM else logging.WARNING
            if severity == Severity.WARNING
            else logging.INFO,
            "%s: %s",
            severity,
            message,
        )
        return event

    def _publish_alert_record(self, record: AlertRecord) -> None:
        event = AlertEvent(
            alert_id=record.id,
            shipment_id=record.shipment_id,
            timestamp=record.timestamp,
            severity=record.severity,
            alert_type=record.alert_type,
            message=record.message,
            acknowledged=record.acknowledged,
        )
        self._mqtt.publish(self.topics.alert_events, event, qos=1)

    def _request_relay_state(self, state: RelayState) -> None:
        now = time.monotonic()
        if (
            self._pending_relay_state == state
            and now - self._pending_relay_at < self.COMMAND_RETRY_SECONDS
        ):
            return
        command = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command=state,
            source=CommandSource.AUTO,
        )
        if self._mqtt.publish(self.topics.cooling_set, command, qos=1):
            self._pending_relay_state = state
            self._pending_relay_at = now
            self._logger.info("Cooling command requested: %s", state)

    def _timer_loop(self) -> None:
        while not self._stop_event.wait(0.5):
            try:
                with self._lock:
                    evaluation = self.rules.poll_time_rules()
                    if evaluation.alerts or evaluation.requested_relay_state is not None:
                        self._handle_evaluation(evaluation)
                        self.publish_snapshot()
            except Exception:
                self._logger.exception("Timed rule evaluation failed")


def _configure_logger(config: AppConfig) -> logging.Logger:
    logger = logging.getLogger("coldchain_guardian.data_manager")
    logger.setLevel(getattr(logging, config.logging.level, logging.INFO))
    log_path: Path = config.logging.data_manager_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_path = str(log_path.resolve())
    has_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and handler.baseFilename == resolved_path
        for handler in logger.handlers
    )
    if not has_file_handler:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    return logger


def main() -> int:
    config = load_config()
    manager = DataManager(config)
    stop_event = Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    manager.start()
    try:
        while not stop_event.wait(0.5):
            pass
    finally:
        manager.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
