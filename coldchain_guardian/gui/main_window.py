"""Main GUI application and MQTT-to-Qt bridge."""

from __future__ import annotations

import logging
import sqlite3
import sys
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget

from coldchain_guardian.config import AppConfig, load_config
from coldchain_guardian.contracts import (
    CommandMessage,
    CommandSource,
    ControlMode,
    RelayState,
    Severity,
    decode_payload,
    now_iso,
)
from coldchain_guardian.database.db_manager import DatabaseManager
from coldchain_guardian.gui.dashboard import DashboardWidget
from coldchain_guardian.gui.history import HistoryWidget
from coldchain_guardian.gui.models import AlertView, DashboardSnapshot, ViewModelError
from coldchain_guardian.gui.theme import STYLESHEET
from coldchain_guardian.mqtt_client import ManagedMqttClient
from coldchain_guardian.topics import TopicRegistry


class MqttQtBridge(QObject):
    snapshot_received = Signal(dict)
    alert_received = Signal(dict)
    connection_changed = Signal(bool)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.topics = TopicRegistry(config.shipment.id)
        self.client = ManagedMqttClient(
            client_id=f"coldchain-gui-{config.shipment.id}",
            config=config.mqtt,
            subscriptions=(
                (self.topics.state_snapshot, 1),
                (self.topics.alert_events, 1),
            ),
            on_message=self._on_message,
            on_connection_change=self.connection_changed.emit,
        )

    def _on_message(self, topic: str, raw_payload: bytes) -> None:
        try:
            payload = decode_payload(raw_payload)
        except ValueError:
            logging.getLogger(__name__).exception("Invalid GUI MQTT payload")
            return
        if topic == self.topics.state_snapshot:
            self.snapshot_received.emit(payload)
        elif topic == self.topics.alert_events:
            self.alert_received.emit(payload)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.topics = TopicRegistry(config.shipment.id)
        self.database = DatabaseManager(config.database.path)
        self.bridge = MqttQtBridge(config)
        self._mode = ControlMode.AUTO

        self.setWindowTitle("ColdChain Guardian")
        self.setMinimumSize(1180, 760)
        self.dashboard = DashboardWidget(config)
        self.history = HistoryWidget(
            self.database, row_limit=config.gui.history_row_limit
        )
        tabs = QTabWidget()
        tabs.addTab(self.dashboard, "Dashboard")
        tabs.addTab(self.history, "History")
        tabs.currentChanged.connect(
            lambda index: self.history.refresh() if index == 1 else None
        )
        self.setCentralWidget(tabs)
        self.setStyleSheet(STYLESHEET)

        self.bridge.snapshot_received.connect(self._on_snapshot)
        self.bridge.alert_received.connect(self._on_alert)
        self.dashboard.mode_requested.connect(self._request_mode)
        self.dashboard.cooling_requested.connect(self._request_cooling)
        self.dashboard.acknowledge_requested.connect(self._request_ack)
        self.dashboard.reset_requested.connect(self._request_reset)

        self._load_recent_alerts()
        self.bridge.client.start()

    def _load_recent_alerts(self) -> None:
        try:
            records = self.database.recent_alerts(limit=50)
        except sqlite3.Error:
            return
        alerts = [
            AlertView(
                alert_id=record.id,
                timestamp=record.timestamp,
                severity=_severity(record.severity),
                alert_type=record.alert_type,
                message=record.message,
                acknowledged=record.acknowledged,
            )
            for record in records
        ]
        self.dashboard.set_alerts(alerts)

    def _on_snapshot(self, payload: dict[str, Any]) -> None:
        try:
            snapshot = DashboardSnapshot.from_payload(
                payload, expected_shipment_id=self.config.shipment.id
            )
        except ViewModelError as exc:
            logging.getLogger(__name__).warning("Rejected GUI snapshot: %s", exc)
            return
        self._mode = snapshot.control_mode
        self.dashboard.update_snapshot(snapshot)

    def _on_alert(self, payload: dict[str, Any]) -> None:
        try:
            alert = AlertView.from_payload(
                payload, expected_shipment_id=self.config.shipment.id
            )
        except ViewModelError as exc:
            logging.getLogger(__name__).warning("Rejected GUI alert: %s", exc)
            return
        self.dashboard.add_or_update_alert(alert)

    def _request_mode(self, mode_value: str) -> None:
        mode = ControlMode(mode_value)
        command = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command=mode,
            source=CommandSource.MANUAL,
        )
        self.bridge.client.publish(self.topics.control_mode_set, command, qos=1)

    def _request_cooling(self, state_value: str) -> None:
        if self._mode != ControlMode.MANUAL:
            QMessageBox.information(
                self,
                "Manual mode required",
                "Switch to MANUAL mode before controlling the relay.",
            )
            return
        command = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command=RelayState(state_value),
            source=CommandSource.MANUAL,
        )
        self.bridge.client.publish(self.topics.cooling_set, command, qos=1)

    def _request_ack(self, alert_id: int) -> None:
        self.bridge.client.publish(
            self.topics.alert_ack_set,
            {
                "schema_version": 1,
                "shipment_id": self.config.shipment.id,
                "timestamp": now_iso(),
                "alert_id": alert_id,
            },
            qos=1,
        )

    def _request_reset(self) -> None:
        command = CommandMessage.create(
            shipment_id=self.config.shipment.id,
            command="RESET",
            source=CommandSource.RESET,
        )
        self.bridge.client.publish(self.topics.demo_reset_set, command, qos=1)

    def closeEvent(self, event) -> None:
        self.bridge.client.stop()
        event.accept()


def _severity(value: str) -> Severity:
    return Severity(value)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    application = QApplication(sys.argv)
    try:
        window = MainWindow(load_config())
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
