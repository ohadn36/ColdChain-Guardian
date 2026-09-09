"""DHT-style temperature and humidity emulator."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import random
from threading import Event, Lock, Thread
from typing import Any

from coldchain_guardian.config import AppConfig
from coldchain_guardian.contracts import (
    CommandSource,
    SensorReading,
    decode_payload,
    now_iso,
)
from coldchain_guardian.data_manager.validator import (
    MessageValidationError,
    validate_command_message,
    validate_temperature_override,
)
from coldchain_guardian.mqtt_client import ManagedMqttClient
from coldchain_guardian.topics import TopicRegistry


@dataclass(frozen=True)
class DhtSnapshot:
    temperature_c: float
    humidity_percent: float
    override_enabled: bool
    override_target_c: float | None


class DhtEmulator:
    """Publish slowly changing readings, with an MQTT-controlled demo override."""

    def __init__(
        self,
        config: AppConfig,
        *,
        mqtt_client: ManagedMqttClient | Any | None = None,
        random_seed: int | None = None,
    ) -> None:
        self.config = config
        self.topics = TopicRegistry(config.shipment.id)
        self._logger = logging.getLogger(__name__)
        self._random = random.Random(random_seed)
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._temperature_c = config.emulation.initial_temperature_c
        self._humidity_percent = config.emulation.initial_humidity_percent
        self._override_enabled = False
        self._override_target_c: float | None = None
        self._mqtt = mqtt_client or ManagedMqttClient(
            client_id=f"coldchain-dht-{config.shipment.id}",
            config=config.mqtt,
            subscriptions=(
                (self.topics.dht_override_set, 1),
                (self.topics.demo_reset_set, 1),
            ),
            on_message=self._on_message,
            logger=self._logger,
        )

    @property
    def is_connected(self) -> bool:
        return bool(self._mqtt.is_connected)

    def snapshot(self) -> DhtSnapshot:
        with self._lock:
            return DhtSnapshot(
                temperature_c=self._temperature_c,
                humidity_percent=self._humidity_percent,
                override_enabled=self._override_enabled,
                override_target_c=self._override_target_c,
            )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._mqtt.start()
        self._thread = Thread(target=self._publish_loop, name="dht-emulator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.config.emulation.publish_interval_seconds + 1)
        self._mqtt.stop()

    def publish_once(self, *, advance: bool = True) -> None:
        snapshot = self._advance_readings() if advance else self.snapshot()
        temperature = SensorReading.create(
            device_id=self.config.devices.temperature_sensor_id,
            shipment_id=self.config.shipment.id,
            sensor_type="temperature",
            value=round(snapshot.temperature_c, 2),
            unit="C",
        )
        humidity = SensorReading.create(
            device_id=self.config.devices.humidity_sensor_id,
            shipment_id=self.config.shipment.id,
            sensor_type="humidity",
            value=round(snapshot.humidity_percent, 2),
            unit="%",
        )
        self._mqtt.publish(self.topics.temperature, temperature, qos=0)
        self._mqtt.publish(self.topics.humidity, humidity, qos=0)

    def reset(self) -> None:
        with self._lock:
            self._temperature_c = self.config.emulation.initial_temperature_c
            self._humidity_percent = self.config.emulation.initial_humidity_percent
            self._override_enabled = False
            self._override_target_c = None
        self._publish_override_status()
        self.publish_once(advance=False)

    def _publish_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.publish_once()
            except Exception:
                self._logger.exception("Unable to publish DHT reading")
            self._stop_event.wait(self.config.emulation.publish_interval_seconds)

    def _advance_readings(self) -> DhtSnapshot:
        emulation = self.config.emulation
        with self._lock:
            if self._override_enabled and self._override_target_c is not None:
                self._temperature_c = self._override_target_c
            else:
                temperature_correction = (
                    emulation.initial_temperature_c - self._temperature_c
                ) * 0.08
                self._temperature_c += temperature_correction + self._random.uniform(
                    -emulation.temperature_drift_step_c,
                    emulation.temperature_drift_step_c,
                )
                self._temperature_c = min(
                    emulation.temperature_max_c,
                    max(emulation.temperature_min_c, self._temperature_c),
                )

            humidity_correction = (
                emulation.initial_humidity_percent - self._humidity_percent
            ) * 0.08
            self._humidity_percent += humidity_correction + self._random.uniform(
                -emulation.humidity_drift_step_percent,
                emulation.humidity_drift_step_percent,
            )
            self._humidity_percent = min(100.0, max(0.0, self._humidity_percent))
            return self.snapshot_unlocked()

    def snapshot_unlocked(self) -> DhtSnapshot:
        return DhtSnapshot(
            temperature_c=self._temperature_c,
            humidity_percent=self._humidity_percent,
            override_enabled=self._override_enabled,
            override_target_c=self._override_target_c,
        )

    def _on_message(self, topic: str, raw_payload: bytes) -> None:
        try:
            payload = decode_payload(raw_payload)
            if topic == self.topics.dht_override_set:
                override = validate_temperature_override(
                    payload,
                    expected_shipment_id=self.config.shipment.id,
                    minimum_c=self.config.emulation.temperature_min_c,
                    maximum_c=self.config.emulation.temperature_max_c,
                )
                with self._lock:
                    self._override_enabled = override.enabled
                    self._override_target_c = override.target_temperature_c
                self._publish_override_status()
                self.publish_once()
            elif topic == self.topics.demo_reset_set:
                validate_command_message(
                    payload,
                    expected_shipment_id=self.config.shipment.id,
                    allowed_commands={"RESET"},
                    allowed_sources={CommandSource.RESET},
                )
                self.reset()
        except (ValueError, MessageValidationError):
            self._logger.exception("Rejected DHT control message on %s", topic)

    def _publish_override_status(self) -> None:
        snapshot = self.snapshot()
        self._mqtt.publish(
            self.topics.dht_override_status,
            {
                "schema_version": 1,
                "shipment_id": self.config.shipment.id,
                "timestamp": now_iso(),
                "enabled": snapshot.override_enabled,
                "target_temperature_c": snapshot.override_target_c,
                "source": "DHT",
            },
            qos=1,
            retain=True,
        )
