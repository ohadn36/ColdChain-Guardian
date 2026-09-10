"""Live dashboard tab for the main desktop application."""

from __future__ import annotations

import time

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
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
from coldchain_guardian.contracts import (
    ControlMode,
    DoorState,
    RelayState,
    Severity,
    parse_timestamp,
)
from coldchain_guardian.gui.models import AlertView, DashboardSnapshot
from coldchain_guardian.gui.theme import (
    BACKGROUND,
    Tone,
    tone_for_status,
    tone_hex,
    tone_rgb,
)
from coldchain_guardian.gui.widgets import AlertBanner, StatusCard, StatusPill


class DashboardWidget(QWidget):
    mode_requested = Signal(str)
    cooling_requested = Signal(str)
    acknowledge_requested = Signal(int)
    reset_requested = Signal()

    ALERT_ROWS = 50
    STALE_AFTER_SECONDS = 10.0

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._temperatures: list[float] = []
        self._times: list[float] = []
        self._alerts: dict[int, AlertView] = {}
        self._last_snapshot_at: float | None = None

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addLayout(self._build_header())
        self.banner = AlertBanner()
        root.addWidget(self.banner)
        root.addLayout(self._build_cards())
        middle = QHBoxLayout()
        middle.addWidget(self._build_chart(), stretch=3)
        middle.addWidget(self._build_controls(), stretch=1)
        root.addLayout(middle, stretch=3)
        root.addWidget(self._build_alerts(), stretch=2)

        self._freshness_timer = QTimer(self)
        self._freshness_timer.setInterval(1000)
        self._freshness_timer.timeout.connect(self._refresh_freshness)
        self._freshness_timer.start()
        self._refresh_freshness()

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title = QLabel("COLDCHAIN GUARDIAN")
        title.setObjectName("appTitle")
        subtitle = QLabel(f"Shipment {self.config.shipment.id}")
        subtitle.setObjectName("subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        layout.addLayout(title_block)
        layout.addStretch()

        self.freshness_pill = StatusPill("NO DATA YET", Tone.UNKNOWN)
        self.mqtt_pill = StatusPill("MQTT OFFLINE", Tone.ALARM)
        self.database_pill = StatusPill("DATABASE UNKNOWN", Tone.UNKNOWN)
        self.mode_pill = StatusPill("AUTO MODE", Tone.INFO)
        for pill in (
            self.freshness_pill,
            self.mqtt_pill,
            self.database_pill,
            self.mode_pill,
        ):
            layout.addWidget(pill)
        return layout

    def _build_cards(self) -> QGridLayout:
        rules = self.config.rules
        layout = QGridLayout()
        layout.setSpacing(10)
        self.temperature_card = StatusCard(
            "Temperature",
            detail=(
                f"Safe range {rules.temperature_min_c:.0f} – "
                f"{rules.temperature_warning_high_c:.0f} °C"
            ),
        )
        self.humidity_card = StatusCard(
            "Humidity",
            detail=(
                f"Safe range {rules.humidity_min_percent:.0f} – "
                f"{rules.humidity_max_percent:.0f} %"
            ),
        )
        self.door_card = StatusCard(
            "Door",
            detail=f"Warning after {rules.door_warning_after_seconds} s open",
        )
        self.cooling_card = StatusCard("Cooling", detail="AUTO control")
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
        rules = self.config.rules
        group = QGroupBox("Temperature over time")
        layout = QVBoxLayout(group)
        self.plot = pg.PlotWidget(
            background=BACKGROUND,
            axisItems={"bottom": pg.DateAxisItem(orientation="bottom")},
        )
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setLabel("left", "Temperature", units="°C")
        self.plot.setMouseEnabled(x=False, y=False)

        red, green, blue = tone_rgb(Tone.NORMAL)
        safe_band = pg.LinearRegionItem(
            values=(rules.temperature_min_c, rules.temperature_warning_high_c),
            orientation="horizontal",
            movable=False,
            brush=pg.mkBrush(red, green, blue, 36),
            pen=pg.mkPen(None),
        )
        safe_band.setZValue(-10)
        self.plot.addItem(safe_band)

        for value, tone, label in (
            (
                rules.temperature_min_c,
                Tone.WARNING,
                f"{rules.temperature_min_c:.0f} °C min",
            ),
            (
                rules.temperature_warning_high_c,
                Tone.WARNING,
                f"{rules.temperature_warning_high_c:.0f} °C warning",
            ),
            (
                rules.temperature_alarm_high_c,
                Tone.ALARM,
                f"{rules.temperature_alarm_high_c:.0f} °C alarm",
            ),
        ):
            self.plot.addItem(
                pg.InfiniteLine(
                    pos=value,
                    angle=0,
                    pen=pg.mkPen(
                        tone_hex(tone), width=1, style=Qt.PenStyle.DashLine
                    ),
                    label=label,
                    labelOpts={"color": tone_hex(tone), "position": 0.04},
                )
            )

        self.temperature_curve = self.plot.plot(
            pen=pg.mkPen(tone_hex(Tone.INFO), width=3), symbol="o", symbolSize=5
        )
        layout.addWidget(self.plot)
        return group

    def _build_controls(self) -> QGroupBox:
        group = QGroupBox("Controls")
        layout = QVBoxLayout(group)
        self.auto_button = QRadioButton("AUTO")
        self.auto_button.setToolTip(
            "The rules engine switches cooling on above "
            f"{self.config.rules.temperature_warning_high_c:.0f} °C and off below "
            f"{self.config.rules.cooling_off_below_c:.0f} °C."
        )
        self.manual_button = QRadioButton("MANUAL")
        self.manual_button.setToolTip("Only operator commands change the relay.")
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
        self.reset_button.setToolTip(
            "Return the live demo to 5 °C, closed door, cooling off, AUTO mode. "
            "Stored history is never deleted."
        )
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
        header = self.alert_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.alert_table.verticalHeader().setVisible(False)
        self.alert_table.setMinimumHeight(190)
        self.alert_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.alert_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.alert_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.alert_table.itemSelectionChanged.connect(self._refresh_ack_button)

        self.acknowledge_button = QPushButton("ACKNOWLEDGE SELECTED ALERT")
        self.acknowledge_button.setToolTip("Select a row in the table first.")
        self.acknowledge_button.clicked.connect(self._acknowledge_selected)
        self.acknowledge_button.setEnabled(False)
        layout.addWidget(self.alert_table)
        layout.addWidget(self.acknowledge_button)
        return group

    def update_snapshot(self, snapshot: DashboardSnapshot) -> None:
        self._last_snapshot_at = time.monotonic()
        self._update_cards(snapshot)
        self._update_header(snapshot)
        self._update_chart(snapshot)
        self._refresh_freshness()

    def _update_cards(self, snapshot: DashboardSnapshot) -> None:
        temperature = (
            "-- °C"
            if snapshot.temperature_c is None
            else f"{snapshot.temperature_c:.1f} °C"
        )
        self.temperature_card.update_reading(
            value=temperature,
            badge=snapshot.temperature_status.replace("_", " "),
            tone=tone_for_status(snapshot.temperature_status),
        )

        humidity = (
            "-- %"
            if snapshot.humidity_percent is None
            else f"{snapshot.humidity_percent:.1f} %"
        )
        self.humidity_card.update_reading(
            value=humidity,
            badge=snapshot.humidity_status.replace("_", " "),
            tone=tone_for_status(snapshot.humidity_status),
        )

        door_open = snapshot.door_state == DoorState.OPEN
        self.door_card.update_reading(
            value=str(snapshot.door_state),
            badge="ATTENTION" if door_open else "NORMAL",
            tone=tone_for_status(str(snapshot.door_state)),
        )

        cooling_on = snapshot.cooling_state == RelayState.ON
        self.cooling_card.update_reading(
            value=str(snapshot.cooling_state),
            badge="ACTIVE" if cooling_on else "IDLE",
            tone=tone_for_status(str(snapshot.cooling_state)),
            detail=f"{snapshot.control_mode} control",
        )

    def _update_header(self, snapshot: DashboardSnapshot) -> None:
        self.mqtt_pill.update_state(
            "MQTT CONNECTED" if snapshot.mqtt_connected else "MQTT OFFLINE",
            Tone.NORMAL if snapshot.mqtt_connected else Tone.ALARM,
        )
        self.database_pill.update_state(
            "DATABASE ONLINE" if snapshot.database_online else "DATABASE OFFLINE",
            Tone.NORMAL if snapshot.database_online else Tone.ALARM,
        )
        self.mode_pill.update_state(f"{snapshot.control_mode} MODE", Tone.INFO)

        automatic = snapshot.control_mode == ControlMode.AUTO
        self.auto_button.setChecked(automatic)
        self.manual_button.setChecked(not automatic)
        self._set_manual_controls(not automatic)

    def _update_chart(self, snapshot: DashboardSnapshot) -> None:
        if snapshot.temperature_c is None:
            return
        self._times.append(parse_timestamp(snapshot.timestamp).timestamp())
        self._temperatures.append(snapshot.temperature_c)
        retained = self.config.gui.chart_history_points
        del self._times[:-retained]
        del self._temperatures[:-retained]
        self.temperature_curve.setData(self._times, self._temperatures)

        # Keep every threshold line on screen even when readings stay normal.
        rules = self.config.rules
        self.plot.setYRange(
            min([*self._temperatures, rules.temperature_min_c - 2.0]),
            max([*self._temperatures, rules.temperature_alarm_high_c + 2.0]),
            padding=0.05,
        )

    def _refresh_freshness(self) -> None:
        if self._last_snapshot_at is None:
            self.freshness_pill.update_state("NO DATA YET", Tone.UNKNOWN)
            return
        elapsed = time.monotonic() - self._last_snapshot_at
        self.freshness_pill.update_state(
            f"UPDATED {elapsed:.0f}S AGO",
            Tone.NORMAL if elapsed <= self.STALE_AFTER_SECONDS else Tone.WARNING,
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
        )[: self.ALERT_ROWS]
        self.alert_table.setRowCount(len(alerts))
        for row, alert in enumerate(alerts):
            tone = tone_for_status(str(alert.severity))
            background = QColor(*tone_rgb(tone))
            background.setAlpha(24 if alert.acknowledged else 52)
            values = (
                parse_timestamp(alert.timestamp).astimezone().strftime("%H:%M:%S"),
                str(alert.severity),
                alert.message,
                "YES" if alert.acknowledged else "NO",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, alert.alert_id)
                item.setBackground(background)
                if column == 1:
                    item.setForeground(QColor(tone_hex(tone)))
                self.alert_table.setItem(row, column, item)
        self._refresh_banner()
        self._refresh_ack_button()

    def _refresh_banner(self) -> None:
        """Show the newest unacknowledged alarm, else warning, else all-clear."""

        unacknowledged = [
            alert for alert in self._alerts.values() if not alert.acknowledged
        ]
        for severity, tone in (
            (Severity.ALARM, Tone.ALARM),
            (Severity.WARNING, Tone.WARNING),
        ):
            matching = [
                alert for alert in unacknowledged if alert.severity == severity
            ]
            if not matching:
                continue
            newest = max(matching, key=lambda alert: alert.alert_id)
            remaining = len(matching) - 1
            self.banner.show_state(
                tone=tone,
                severity=str(severity),
                headline=newest.message,
                detail=(
                    f"{remaining} more unacknowledged"
                    if remaining
                    else "Awaiting acknowledgement"
                ),
            )
            return
        self.banner.show_normal()

    def _selected_alert_id(self) -> int | None:
        item = self.alert_table.item(self.alert_table.currentRow(), 0)
        if item is None or not self.alert_table.selectionModel().hasSelection():
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_ack_button(self) -> None:
        self.acknowledge_button.setEnabled(self._selected_alert_id() is not None)

    def _acknowledge_selected(self) -> None:
        alert_id = self._selected_alert_id()
        if alert_id is not None:
            self.acknowledge_requested.emit(alert_id)

    def _set_manual_controls(self, enabled: bool) -> None:
        tooltip = (
            ""
            if enabled
            else "Switch to MANUAL mode to command the relay directly."
        )
        for button in (self.cooling_on_button, self.cooling_off_button):
            button.setEnabled(enabled)
            button.setToolTip(tooltip)
