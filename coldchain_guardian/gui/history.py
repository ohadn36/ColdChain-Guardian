"""SQLite-backed history tab."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from coldchain_guardian.database.db_manager import DatabaseManager


class HistoryWidget(QWidget):
    def __init__(self, database: DatabaseManager, *, row_limit: int) -> None:
        super().__init__()
        self.database = database
        self.row_limit = row_limit
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("HISTORY — loaded directly from SQLite")
        title.setObjectName("sectionTitle")
        refresh = QPushButton("REFRESH")
        refresh.clicked.connect(self.refresh)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(refresh)
        layout.addLayout(header)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.tabs = QTabWidget()
        self.readings_table = self._table(
            ["Time", "Sensor", "Value", "Unit", "Device"]
        )
        self.alerts_table = self._table(
            ["Time", "Severity", "Type", "Message", "ACK"]
        )
        self.actuators_table = self._table(
            ["Time", "Device", "State", "Source"]
        )
        self.tabs.addTab(self.readings_table, "Sensor readings")
        self.tabs.addTab(self.alerts_table, "Alerts")
        self.tabs.addTab(self.actuators_table, "Actuator events")
        layout.addWidget(self.tabs)
        self.refresh()

    def refresh(self) -> None:
        try:
            readings = self.database.recent_readings(limit=self.row_limit)
            alerts = self.database.recent_alerts(limit=self.row_limit)
            actuators = self.database.recent_actuator_events(limit=self.row_limit)
        except sqlite3.Error as exc:
            self.status_label.setText(f"Database unavailable: {exc}")
            return

        self._fill(
            self.readings_table,
            [
                (
                    reading.timestamp,
                    reading.sensor_type,
                    f"{reading.value:.2f}",
                    reading.unit,
                    reading.device_id,
                )
                for reading in readings
            ],
        )
        self._fill(
            self.alerts_table,
            [
                (
                    alert.timestamp,
                    alert.severity,
                    alert.alert_type,
                    alert.message,
                    "YES" if alert.acknowledged else "NO",
                )
                for alert in alerts
            ],
        )
        self._fill(
            self.actuators_table,
            [
                (
                    event.timestamp,
                    event.device_id,
                    event.state,
                    event.source,
                )
                for event in actuators
            ],
        )
        self.status_label.setText(
            f"Loaded {len(readings)} readings, {len(alerts)} alerts, "
            f"and {len(actuators)} actuator events"
        )

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return table

    @staticmethod
    def _fill(table: QTableWidget, rows: list[tuple[str, ...]]) -> None:
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column_index, value in enumerate(values):
                table.setItem(row_index, column_index, QTableWidgetItem(str(value)))

