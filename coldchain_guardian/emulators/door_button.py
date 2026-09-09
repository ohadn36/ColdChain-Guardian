"""OPEN/CLOSED shipment-door button emulator."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from coldchain_guardian.config import AppConfig
from coldchain_guardian.contracts import (
    CommandSource,
    DeviceStateMessage,
    DoorState,
    decode_payload,
)
from coldchain_guardian.data_manager.validator import (
    MessageValidationError,
    validate_command_message,
)
from coldchain_guardian.mqtt_client import ManagedMqttClient
from coldchain_guardian.topics import TopicRegistry


class DoorButtonEmulator:
    def __init__(
        self,
        config: AppConfig,
        *,
        mqtt_client: ManagedMqttClient | Any | None = None,
    ) -> None:
        self.config = config
        self.topics = TopicRegistry(config.shipment.id)
        self._logger = logging.getLogger(__name__)
        self._lock = Lock()
        self._state = DoorState.CLOSED
        self._mqtt = mqtt_client or ManagedMqttClient(
            client_id=f"coldchain-door-{config.shipment.id}",
            config=config.mqtt,
            subscriptions=((self.topics.demo_reset_set, 1),),
            on_message=self._on_message,
            logger=self._logger,
        )

    @property
    def state(self) -> DoorState:
        with self._lock:
            return self._state

    @property
    def is_connected(self) -> bool:
        return bool(self._mqtt.is_connected)

    def start(self) -> None:
        self._mqtt.start()
        self.publish_state()

    def stop(self) -> None:
        self._mqtt.stop()

    def set_state(self, state: DoorState) -> None:
        with self._lock:
            self._state = state
        self.publish_state()

    def toggle(self) -> DoorState:
        next_state = DoorState.CLOSED if self.state == DoorState.OPEN else DoorState.OPEN
        self.set_state(next_state)
        return next_state

    def publish_state(self) -> None:
        message = DeviceStateMessage.create(
            device_id=self.config.devices.door_sensor_id,
            shipment_id=self.config.shipment.id,
            state=self.state,
        )
        self._mqtt.publish(self.topics.door, message, qos=1, retain=True)

    def _on_message(self, topic: str, raw_payload: bytes) -> None:
        if topic != self.topics.demo_reset_set:
            return
        try:
            validate_command_message(
                decode_payload(raw_payload),
                expected_shipment_id=self.config.shipment.id,
                allowed_commands={"RESET"},
                allowed_sources={CommandSource.RESET},
            )
            self.set_state(DoorState.CLOSED)
        except (ValueError, MessageValidationError):
            self._logger.exception("Rejected door reset message")

