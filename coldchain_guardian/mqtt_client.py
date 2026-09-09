"""Small managed wrapper around Eclipse Paho MQTT."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import logging
from threading import Event, Lock
from typing import Any, Protocol

from coldchain_guardian.config import MqttConfig
from coldchain_guardian.contracts import encode_payload


try:
    import paho.mqtt.client as mqtt
except ModuleNotFoundError:  # The error is explained when a client is constructed.
    mqtt = None  # type: ignore[assignment]


MessageHandler = Callable[[str, bytes], None]
ConnectionHandler = Callable[[bool], None]


class _ClientFactory(Protocol):
    def __call__(self, client_id: str) -> Any: ...


class ManagedMqttClient:
    """Manage connection lifecycle, subscriptions, and JSON publishing."""

    def __init__(
        self,
        *,
        client_id: str,
        config: MqttConfig,
        subscriptions: Iterable[tuple[str, int]] = (),
        on_message: MessageHandler | None = None,
        on_connection_change: ConnectionHandler | None = None,
        client_factory: _ClientFactory | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.client_id = client_id
        self.config = config
        self.subscriptions = tuple(subscriptions)
        self._message_handler = on_message
        self._connection_handler = on_connection_change
        self._logger = logger or logging.getLogger(__name__)
        self._connected = Event()
        self._started = False
        self._lifecycle_lock = Lock()

        if client_factory is not None:
            self._client = client_factory(client_id)
        else:
            if mqtt is None:
                raise RuntimeError(
                    "paho-mqtt is not installed. Install project requirements first."
                )
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                protocol=mqtt.MQTTv311,
            )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(
            min_delay=config.reconnect_min_delay_seconds,
            max_delay=config.reconnect_max_delay_seconds,
        )

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def start(self, *, wait_timeout: float = 5.0) -> bool:
        """Start the network loop and return whether the first connection succeeded."""

        with self._lifecycle_lock:
            if self._started:
                return self.is_connected
            self._client.connect_async(
                self.config.host,
                self.config.port,
                self.config.keepalive_seconds,
            )
            self._client.loop_start()
            self._started = True
        return self._connected.wait(timeout=wait_timeout)

    def stop(self) -> None:
        with self._lifecycle_lock:
            if not self._started:
                return
            try:
                self._client.disconnect()
            finally:
                self._client.loop_stop()
                self._connected.clear()
                self._started = False

    def publish(
        self,
        topic: str,
        payload: Mapping[str, Any] | object,
        *,
        qos: int = 1,
        retain: bool = False,
    ) -> bool:
        """Publish a JSON payload and report whether Paho accepted it."""

        result = self._client.publish(
            topic,
            payload=encode_payload(payload),
            qos=qos,
            retain=retain,
        )
        accepted = getattr(result, "rc", 1) == 0
        if not accepted:
            self._logger.warning("MQTT publish rejected for topic %s", topic)
        return accepted

    def _on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        del userdata, flags, properties
        if reason_code != 0:
            self._logger.error("MQTT connection failed: %s", reason_code)
            return
        for topic, qos in self.subscriptions:
            client.subscribe(topic, qos=qos)
        self._connected.set()
        self._logger.info("MQTT connected as %s", self.client_id)
        if self._connection_handler is not None:
            self._connection_handler(True)

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        del client, userdata, disconnect_flags, properties
        self._connected.clear()
        if reason_code == 0:
            self._logger.info("MQTT disconnected cleanly")
        else:
            self._logger.warning("MQTT disconnected: %s", reason_code)
        if self._connection_handler is not None:
            self._connection_handler(False)

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        del client, userdata
        if self._message_handler is None:
            return
        try:
            self._message_handler(message.topic, bytes(message.payload))
        except Exception:
            self._logger.exception("Unhandled MQTT message callback error on %s", message.topic)
