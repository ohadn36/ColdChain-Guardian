"""Temperature override knob emulator."""

from __future__ import annotations

from typing import Any

from coldchain_guardian.config import AppConfig
from coldchain_guardian.contracts import (
    CommandMessage,
    CommandSource,
    TemperatureOverrideCommand,
)
from coldchain_guardian.mqtt_client import ManagedMqttClient
from coldchain_guardian.topics import TopicRegistry


class TemperatureKnobEmulator:
    def __init__(
        self,
        config: AppConfig,
        *,
        mqtt_client: ManagedMqttClient | Any | None = None,
    ) -> None:
        self.config = config
        self.topics = TopicRegistry(config.shipment.id)
        self._mqtt = mqtt_client or ManagedMqttClient(
            client_id=f"coldchain-knob-{config.shipment.id}",
            config=config.mqtt,
        )

    @property
    def is_connected(self) -> bool:
        return bool(self._mqtt.is_connected)

    def start(self) -> None:
        self._mqtt.start()

    def stop(self) -> None:
        self._mqtt.stop()

    def set_temperature(self, target_c: float) -> None:
        minimum = self.config.emulation.temperature_min_c
        maximum = self.config.emulation.temperature_max_c
        if not minimum <= target_c <= maximum:
            raise ValueError(f"temperature must be between {minimum} and {maximum}")
        command = TemperatureOverrideCommand.create(
            shipment_id=self.config.shipment.id,
            enabled=True,
            target_temperature_c=target_c,
        )
        self._mqtt.publish(self.topics.dht_override_set, command, qos=1)

    def release_override(self) -> None:
        command = TemperatureOverrideCommand.create(
            shipment_id=self.config.shipment.id,
            enabled=False,
            target_temperature_c=None,
        )
        self._mqtt.publish(self.topics.dht_override_set, command, qos=1)

    def reset_demo(self) -> None:
        command = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command="RESET",
            source=CommandSource.RESET,
        )
        self._mqtt.publish(self.topics.demo_reset_set, command, qos=1)

