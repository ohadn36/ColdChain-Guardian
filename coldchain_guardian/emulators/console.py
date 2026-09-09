"""Single demonstration console that hosts four independent MQTT emulators."""

from __future__ import annotations

import logging
import sys

from coldchain_guardian.config import load_config
from coldchain_guardian.contracts import DoorState
from coldchain_guardian.emulators.cooling_relay import CoolingRelayEmulator
from coldchain_guardian.emulators.dht import DhtEmulator
from coldchain_guardian.emulators.door_button import DoorButtonEmulator
from coldchain_guardian.emulators.temperature_knob import TemperatureKnobEmulator


def main() -> int:
    try:
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import (
            QApplication,
            QFrame,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QPushButton,
            QSlider,
            QVBoxLayout,
            QWidget,
        )
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PySide6 is required for the emulator console. Install project requirements."
        ) from exc

    class EmulatorConsole(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.config = load_config()
            self.dht = DhtEmulator(self.config)
            self.door = DoorButtonEmulator(self.config)
            self.knob = TemperatureKnobEmulator(self.config)
            self.relay = CoolingRelayEmulator(self.config)
            self._components = (self.dht, self.door, self.knob, self.relay)

            self.setWindowTitle("ColdChain Guardian — Emulator Console")
            self.setMinimumSize(760, 520)
            central = QWidget()
            layout = QVBoxLayout(central)

            title = QLabel("COLDCHAIN GUARDIAN — EMULATOR CONSOLE")
            title.setObjectName("title")
            layout.addWidget(title)
            self.connection_label = QLabel("MQTT: CONNECTING")
            layout.addWidget(self.connection_label)

            grid = QGridLayout()
            grid.addWidget(self._build_dht_group(QGroupBox, QVBoxLayout, QLabel), 0, 0)
            grid.addWidget(
                self._build_door_group(QGroupBox, QVBoxLayout, QLabel, QPushButton),
                0,
                1,
            )
            grid.addWidget(
                self._build_knob_group(
                    QGroupBox,
                    QVBoxLayout,
                    QHBoxLayout,
                    QLabel,
                    QPushButton,
                    QSlider,
                    Qt,
                ),
                1,
                0,
            )
            grid.addWidget(self._build_relay_group(QGroupBox, QVBoxLayout, QLabel), 1, 1)
            layout.addLayout(grid)

            reset_button = QPushButton("RESET DEMO")
            reset_button.setObjectName("resetButton")
            reset_button.clicked.connect(self._reset_demo)
            layout.addWidget(reset_button)
            layout.addStretch()
            self.setCentralWidget(central)
            self.setStyleSheet(_STYLESHEET)

            for component in self._components:
                component.start()

            self.refresh_timer = QTimer(self)
            self.refresh_timer.timeout.connect(self._refresh)
            self.refresh_timer.start(250)
            self._refresh()

        def _build_dht_group(self, GroupBox, VBoxLayout, Label):
            group = GroupBox("A — DHT Sensor Emulator")
            layout = VBoxLayout(group)
            self.temperature_label = Label("Temperature: -- °C")
            self.humidity_label = Label("Humidity: -- %")
            self.override_label = Label("Override: OFF")
            layout.addWidget(self.temperature_label)
            layout.addWidget(self.humidity_label)
            layout.addWidget(self.override_label)
            return group

        def _build_door_group(self, GroupBox, VBoxLayout, Label, PushButton):
            group = GroupBox("B — Door Button Emulator")
            layout = VBoxLayout(group)
            self.door_label = Label("Door: CLOSED")
            self.door_button = PushButton("OPEN DOOR")
            self.door_button.clicked.connect(self.door.toggle)
            layout.addWidget(self.door_label)
            layout.addWidget(self.door_button)
            return group

        def _build_knob_group(
            self,
            GroupBox,
            VBoxLayout,
            HBoxLayout,
            Label,
            PushButton,
            Slider,
            QtNamespace,
        ):
            group = GroupBox("C — Temperature Knob Emulator")
            layout = VBoxLayout(group)
            self.knob_label = Label("Target: 5.0 °C")
            self.knob_slider = Slider(QtNamespace.Orientation.Horizontal)
            self.knob_slider.setRange(
                round(self.config.emulation.temperature_min_c * 10),
                round(self.config.emulation.temperature_max_c * 10),
            )
            self.knob_slider.setValue(
                round(self.config.emulation.initial_temperature_c * 10)
            )
            self.knob_slider.valueChanged.connect(
                lambda value: self.knob_label.setText(f"Target: {value / 10:.1f} °C")
            )
            buttons = HBoxLayout()
            apply_button = PushButton("APPLY OVERRIDE")
            release_button = PushButton("RELEASE")
            apply_button.clicked.connect(
                lambda: self.knob.set_temperature(self.knob_slider.value() / 10)
            )
            release_button.clicked.connect(self.knob.release_override)
            buttons.addWidget(apply_button)
            buttons.addWidget(release_button)
            layout.addWidget(self.knob_label)
            layout.addWidget(self.knob_slider)
            layout.addLayout(buttons)
            return group

        def _build_relay_group(self, GroupBox, VBoxLayout, Label):
            group = GroupBox("D — Cooling Relay Emulator")
            layout = VBoxLayout(group)
            self.relay_label = Label("Cooling Relay: OFF")
            note = Label("State changes only after an MQTT command.")
            note.setWordWrap(True)
            layout.addWidget(self.relay_label)
            layout.addWidget(note)
            return group

        def _refresh(self) -> None:
            snapshot = self.dht.snapshot()
            self.temperature_label.setText(
                f"Temperature: {snapshot.temperature_c:.1f} °C"
            )
            self.humidity_label.setText(f"Humidity: {snapshot.humidity_percent:.1f} %")
            target = (
                ""
                if snapshot.override_target_c is None
                else f" ({snapshot.override_target_c:.1f} °C)"
            )
            self.override_label.setText(
                f"Override: {'ON' if snapshot.override_enabled else 'OFF'}{target}"
            )
            self.door_label.setText(f"Door: {self.door.state}")
            self.door_button.setText(
                "CLOSE DOOR" if self.door.state == DoorState.OPEN else "OPEN DOOR"
            )
            self.relay_label.setText(f"Cooling Relay: {self.relay.state}")
            connected = sum(component.is_connected for component in self._components)
            self.connection_label.setText(f"MQTT: {connected}/4 EMULATORS CONNECTED")

        def _reset_demo(self) -> None:
            self.knob_slider.setValue(
                round(self.config.emulation.initial_temperature_c * 10)
            )
            self.knob.reset_demo()

        def closeEvent(self, event) -> None:
            for component in reversed(self._components):
                component.stop()
            event.accept()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    application = QApplication(sys.argv)
    window = EmulatorConsole()
    window.show()
    return application.exec()


_STYLESHEET = """
QWidget { background: #0f172a; color: #e2e8f0; font-size: 14px; }
QLabel { background: transparent; }
QLabel#title { font-size: 22px; font-weight: 700; color: #38bdf8; padding: 8px 0; }
QGroupBox {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 12px;
    padding: 14px;
    font-weight: 600;
    background: #1e293b;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QPushButton {
    background: #0369a1; border: none; border-radius: 5px;
    padding: 9px 14px; font-weight: 600;
}
QPushButton:hover { background: #0284c7; }
QPushButton#resetButton { background: #b45309; margin-top: 8px; }
QSlider::groove:horizontal { height: 6px; background: #475569; border-radius: 3px; }
QSlider::handle:horizontal { width: 18px; margin: -6px 0; background: #38bdf8; border-radius: 9px; }
"""


if __name__ == "__main__":
    sys.exit(main())
