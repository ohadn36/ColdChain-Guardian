"""Live dashboard tab for the main desktop application."""

from __future__ import annotations

from datetime import datetime

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from coldchain_guardian.config import AppConfig
from coldchain_guardian.contracts import ControlMode, RelayState, Severity
from coldchain_guardian.gui.models import AlertView, DashboardSnapshot


STATUS_COLORS = {
    "NORMAL": "#22c55e",
    "INFO": "#38bdf8",
    "WARNING": "#f59e0b",
    "WARNING_LOW": "#f59e0b",
    "WARNING_HIGH": "#f59e0b",
    "ALARM": "#ef4444",
    "ALARM_HIGH": "#ef4444",
    "OPEN": "#f59e0b",
    "CLOSED": "#22c55e",
    "ON": "#38bdf8",
    "OFF": "#94a3b8",
    "UNKNOWN": "#64748b",
}


class StatusCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("statusCard")
        layout = QVBoxLayout(self)
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("cardTitle")
        self.value_label = QLabel("--")
        self.value_label.setObjectName("cardValue")
        self.status_label = QLabel("UNKNOWN")
        self.status_label.setObjectName("cardStatus")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.status_label)

    def update_value(self, value: str, status: str) -> None:
        self.value_label.setText(value)
        self.status_label.setText(status.replace("_", " "))
        color = STATUS_COLORS.get(status, STATUS_COLORS["UNKNOWN"])
        self.setStyleSheet(
            f"QFrame#statusCard {{ border-left: 5px solid {color}; }}"
        )


class DashboardWidget(QWidget):
    mode_requested = Signal(str)
    cooling_requested = Signal(str)
    acknowledge_requested = Signal(int)
    reset_requested = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._temperatures: list[float] = []
        self._sample_numbers: list[int] = []
        self._sample_counter = 0
        self._alerts: dict[int, AlertView] = {}

        root = QVBoxLayout(self)
        root.addLayout(self._build_header())
        root.addLayout(self._build_cards())
        middle = QHBoxLayout()
        middle.addWidget(self._build_chart(), stretch=3)
        middle.addWidget(self._build_controls(), stretch=1)
        root.addLayout(middle, stretch=3)
        root.addWidget(self._build_alerts(), stretch=2)

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("COLDCHAIN GUARDIAN")
        title.setObjectName("appTitle")
        subtitle = QLabel(f"Shipment: {self.config.shipment.id}")
        subtitle.setObjectName("subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        layout.addLayout(title_block)
        layout.addStretch()
        self.mqtt_label = QLabel("MQTT ● DISCONNECTED")
        self.database_label = QLabel("DATABASE ● UNKNOWN")
        self.mode_label = QLabel("MODE: AUTO")
        layout.addWidget(self.mqtt_label)
        layout.addWidget(self.database_label)
        layout.addWidget(self.mode_label)
        return layout

    def _build_cards(self) -> QGridLayout:
        layout = QGridLayout()
        self.temperature_card = StatusCard("Temperature")
        self.humidity_card = StatusCard("Humidity")
        self.door_card = StatusCard("Door")
        self.cooling_card = StatusCard("Cooling")
        for column, card in enumerate(
            (
                self.temperature_card,
                self.humidity_card,
                self.door_card,
                self.cooling_card,
            )
        ):
            layout.addWidget(card, 0, column)
        return layout

    def _build_chart(self) -> QGroupBox:
        group = QGroupBox("Temperature over time")
        layout = QVBoxLayout(group)
        self.plot = pg.PlotWidget(background="#0f172a")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setLabel("left", "Temperature", units="°C")
        self.plot.setLabel("bottom", "Reading")
        self.temperature_curve = self.plot.plot(
            pen=pg.mkPen("#38bdf8", width=3), symbol="o", symbolSize=5
        )
        for value, color, label in (
            (self.config.rules.temperature_min_c, "#f59e0b", "minimum"),
            (self.config.rules.temperature_warning_high_c, "#f59e0b", "warning"),
            (self.config.rules.temperature_alarm_high_c, "#ef4444", "alarm"),
        ):
            line = pg.InfiniteLine(
                pos=value,
                angle=0,
                pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine),
                label=label,
            )
            self.plot.addItem(line)
        layout.addWidget(self.plot)
        return group

    def _build_controls(self) -> QGroupBox:
        group = QGroupBox("Controls")
        layout = QVBoxLayout(group)
        self.auto_button = QRadioButton("AUTO")
        self.manual_button = QRadioButton("MANUAL")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.auto_button)
        self.mode_group.addButton(self.manual_button)
        self.auto_button.setChecked(True)
        self.auto_button.clicked.connect(
            lambda: self.mode_requested.emit(ControlMode.AUTO)
        )
        self.manual_button.clicked.connect(
            lambda: self.mode_requested.emit(ControlMode.MANUAL)
        )
        layout.addWidget(self.auto_button)
        layout.addWidget(self.manual_button)

        self.cooling_on_button = QPushButton("COOLING ON")
        self.cooling_off_button = QPushButton("COOLING OFF")
        self.cooling_on_button.clicked.connect(
            lambda: self.cooling_requested.emit(RelayState.ON)
        )
        self.cooling_off_button.clicked.connect(
            lambda: self.cooling_requested.emit(RelayState.OFF)
        )
        layout.addWidget(self.cooling_on_button)
        layout.addWidget(self.cooling_off_button)
        self._set_manual_controls(False)

        layout.addStretch()
        self.reset_button = QPushButton("RESET DEMO")
        self.reset_button.setObjectName("resetButton")
        self.reset_button.clicked.connect(self.reset_requested.emit)
        layout.addWidget(self.reset_button)
        return group

    def _build_alerts(self) -> QGroupBox:
        group = QGroupBox("Recent alerts")
        layout = QVBoxLayout(group)
        self.alert_table = QTableWidget(0, 4)
        self.alert_table.setHorizontalHeaderLabels(
            ["Time", "Severity", "Event", "Acknowledged"]
        )
        self.alert_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.alert_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.alert_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        acknowledge = QPushButton("ACKNOWLEDGE SELECTED ALERT")
        acknowledge.clicked.connect(self._acknowledge_selected)
        layout.addWidget(self.alert_table)
        layout.addWidget(acknowledge)
        return group

    def update_snapshot(self, snapshot: DashboardSnapshot) -> None:
        temperature = (
            "-- °C"
            if snapshot.temperature_c is None
            else f"{snapshot.temperature_c:.1f} °C"
        )
        humidity = (
            "-- %"
            if snapshot.humidity_percent is None
            else f"{snapshot.humidity_percent:.1f} %"
        )
        self.temperature_card.update_value(
            temperature, snapshot.temperature_status
        )
        self.humidity_card.update_value(humidity, snapshot.humidity_status)
        self.door_card.update_value(str(snapshot.door_state), str(snapshot.door_state))
        self.cooling_card.update_value(
            str(snapshot.cooling_state), str(snapshot.cooling_state)
        )

        mqtt_color = "#22c55e" if snapshot.mqtt_connected else "#ef4444"
        database_color = "#22c55e" if snapshot.database_online else "#ef4444"
        self.mqtt_label.setText(
            f"MQTT ● {'CONNECTED' if snapshot.mqtt_connected else 'DISCONNECTED'}"
        )
        self.mqtt_label.setStyleSheet(f"color: {mqtt_color}; font-weight: 700;")
        self.database_label.setText(
            f"DATABASE ● {'ONLINE' if snapshot.database_online else 'OFFLINE'}"
        )
        self.database_label.setStyleSheet(
            f"color: {database_color}; font-weight: 700;"
        )
        self.mode_label.setText(f"MODE: {snapshot.control_mode}")
        if snapshot.control_mode == ControlMode.AUTO:
            self.auto_button.setChecked(True)
            self._set_manual_controls(False)
        else:
            self.manual_button.setChecked(True)
            self._set_manual_controls(True)

        if snapshot.temperature_c is not None:
            self._sample_counter += 1
            self._sample_numbers.append(self._sample_counter)
            self._temperatures.append(snapshot.temperature_c)
            maximum = self.config.gui.chart_history_points
            self._sample_numbers = self._sample_numbers[-maximum:]
            self._temperatures = self._temperatures[-maximum:]
            self.temperature_curve.setData(
                self._sample_numbers, self._temperatures
            )

    def add_or_update_alert(self, alert: AlertView) -> None:
        self._alerts[alert.alert_id] = alert
        self._render_alerts()

    def set_alerts(self, alerts: list[AlertView]) -> None:
        self._alerts = {alert.alert_id: alert for alert in alerts}
        self._render_alerts()

    def _render_alerts(self) -> None:
        alerts = sorted(
            self._alerts.values(), key=lambda alert: alert.alert_id, reverse=True
        )[:50]
        self.alert_table.setRowCount(len(alerts))
        for row, alert in enumerate(alerts):
            time_text = datetime.fromisoformat(
                alert.timestamp.replace("Z", "+00:00")
            ).strftime("%H:%M:%S")
            values = (
                time_text,
                str(alert.severity),
                alert.message,
                "YES" if alert.acknowledged else "NO",
            )
            color = QColor(STATUS_COLORS.get(str(alert.severity), "#94a3b8"))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, alert.alert_id)
                if column == 1:
                    item.setForeground(color)
                self.alert_table.setItem(row, column, item)

    def _acknowledge_selected(self) -> None:
        row = self.alert_table.currentRow()
        if row < 0:
            return
        item = self.alert_table.item(row, 0)
        if item is not None:
            self.acknowledge_requested.emit(int(item.data(Qt.ItemDataRole.UserRole)))

    def _set_manual_controls(self, enabled: bool) -> None:
        self.cooling_on_button.setEnabled(enabled)
        self.cooling_off_button.setEnabled(enabled)
