"""Central MQTT topic registry."""

from __future__ import annotations

from dataclasses import dataclass
import re


_TOPIC_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class TopicRegistry:
    """Build all topics for one shipment without scattered string literals."""

    shipment_id: str

    def __post_init__(self) -> None:
        if not _TOPIC_SEGMENT.fullmatch(self.shipment_id):
            raise ValueError(
                "shipment_id may contain only letters, numbers, underscores, and dashes"
            )

    @property
    def base(self) -> str:
        return f"coldchain/{self.shipment_id}"

    @property
    def temperature(self) -> str:
        return f"{self.base}/sensors/temperature"

    @property
    def humidity(self) -> str:
        return f"{self.base}/sensors/humidity"

    @property
    def door(self) -> str:
        return f"{self.base}/sensors/door"

    @property
    def sensor_wildcard(self) -> str:
        return f"{self.base}/sensors/+"

    @property
    def dht_override_set(self) -> str:
        return f"{self.base}/emulators/dht/override/set"

    @property
    def dht_override_status(self) -> str:
        return f"{self.base}/emulators/dht/override/status"

    @property
    def cooling_set(self) -> str:
        return f"{self.base}/actuators/cooling/set"

    @property
    def cooling_status(self) -> str:
        return f"{self.base}/actuators/cooling/status"

    @property
    def control_mode_set(self) -> str:
        return f"{self.base}/control/mode/set"

    @property
    def state_snapshot(self) -> str:
        return f"{self.base}/state/snapshot"

    @property
    def alert_events(self) -> str:
        return f"{self.base}/alerts/events"

    @property
    def alert_ack_set(self) -> str:
        return f"{self.base}/alerts/ack/set"

    @property
    def demo_reset_set(self) -> str:
        return f"{self.base}/demo/reset/set"

    @property
    def manager_subscriptions(self) -> tuple[str, ...]:
        return (
            self.sensor_wildcard,
            self.cooling_status,
            self.control_mode_set,
            self.alert_ack_set,
            self.demo_reset_set,
        )

