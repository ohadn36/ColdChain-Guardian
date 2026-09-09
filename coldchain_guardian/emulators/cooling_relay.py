"""MQTT-controlled ON/OFF cooling relay emulator."""

from __future__ import annotations

from collections.abc import Callable
import logging
from threading import Lock
from typing import Any

from coldchain_guardian.config import AppConfig
from coldchain_guardian.contracts import (
    CommandSource,
    DeviceStateMessage,
    RelayState,
    decode_payload,
)
from coldchain_guardian.data_manager.validator import (
    MessageValidationError,
    validate_command_message,
)
from coldchain_guardian.mqtt_client import ManagedMqttClient
from coldchain_guardian.topics import TopicRegistry


RelayCallback = Callable[[RelayState], None]


class CoolingRelayEmulator:
    def __init__(
        self,
        config: AppConfig,
        *,
        mqtt_client: ManagedMqttClient | Any | None = None,
        on_state_change: RelayCallback | None = None,
    ) -> None:
        self.config = config
        self.topics = TopicRegistry(config.shipment.id)
        self._logger = logging.getLogger(__name__)
        self._lock = Lock()
        self._state = RelayState.OFF
        self._on_state_change = on_state_change
        self._mqtt = mqtt_client or ManagedMqttClient(
            client_id=f"coldchain-relay-{config.shipment.id}",
            config=config.mqtt,
            subscriptions=(
                (self.topics.cooling_set, 1),
                (self.topics.demo_reset_set, 1),
            ),
            on_message=self._on_message,
            logger=self._logger,
        )

    @property
    def state(self) -> RelayState:
        with self._lock:
            return self._state

    @property
    def is_connected(self) -> bool:
        return bool(self._mqtt.is_connected)

    def start(self) -> None:
        self._mqtt.start()
        self._publish_state(CommandSource.RESET)

    def stop(self) -> None:
        self._mqtt.stop()

    def _apply_command(self, state: RelayState, source: CommandSource) -> None:
        with self._lock:
            changed = state != self._state
            self._state = state
        self._publish_state(source)
        if changed and self._on_state_change is not None:
            self._on_state_change(state)

    def _publish_state(self, source: CommandSource) -> None:
        message = DeviceStateMessage.create(
            device_id=self.config.devices.cooling_relay_id,
            shipment_id=self.config.shipment.id,
            state=self.state,
            source=source,
        )
        self._mqtt.publish(self.topics.cooling_status, message, qos=1, retain=True)

    def _on_message(self, topic: str, raw_payload: bytes) -> None:
        try:
            payload = decode_payload(raw_payload)
            if topic == self.topics.cooling_set:
                command = validate_command_message(
                    payload,
                    expected_shipment_id=self.config.shipment.id,
                    allowed_commands={RelayState.ON, RelayState.OFF},
                    allowed_sources={
                        CommandSource.AUTO,
                        CommandSource.MANUAL,
                        CommandSource.RESET,
                    },
                )
                self._apply_command(
                    RelayState(command.command), CommandSource(command.source)
                )
            elif topic == self.topics.demo_reset_set:
                validate_command_message(
                    payload,
                    expected_shipment_id=self.config.shipment.id,
                    allowed_commands={"RESET"},
                    allowed_sources={CommandSource.RESET},
                )
                self._apply_command(RelayState.OFF, CommandSource.RESET)
        except (ValueError, MessageValidationError):
            self._logger.exception("Rejected cooling relay message on %s", topic)

