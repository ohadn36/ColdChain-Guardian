"""Single demonstration console that hosts four independent MQTT emulators."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
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

from coldchain_guardian.config import load_config
from coldchain_guardian.contracts import DoorState, RelayState
from coldchain_guardian.emulators.cooling_relay import CoolingRelayEmulator
from coldchain_guardian.emulators.dht import DhtEmulator
from coldchain_guardian.emulators.door_button import DoorButtonEmulator
from coldchain_guardian.emulators.temperature_knob import TemperatureKnobEmulator
from coldchain_guardian.gui.theme import STYLESHEET, Tone, tone_for_status
from coldchain_guardian.gui.widgets import StatusCard, StatusPill


class EmulatorConsole(QMainWindow):
    """Four separately implemented emulators presented in one demo window."""

    REFRESH_INTERVAL_MS = 250

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.dht = DhtEmulator(self.config)
        self.door = DoorButtonEmulator(self.config)
        self.knob = TemperatureKnobEmulator(self.config)
        self.relay = CoolingRelayEmulator(self.config)
        self._components = (self.dht, self.door, self.knob, self.relay)

        self.setWindowTitle("ColdChain Guardian — Emulator Console")
        self.setMinimumSize(860, 620)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.addLayout(self._build_header())

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.addWidget(self._build_dht_group(), 0, 0)
        grid.addWidget(self._build_door_group(), 0, 1)
        grid.addWidget(self._build_knob_group(), 1, 0)
        grid.addWidget(self._build_relay_group(), 1, 1)
        layout.addLayout(grid, stretch=1)

        self.reset_button = QPushButton("RESET DEMO")
        self.reset_button.setObjectName("resetButton")
        self.reset_button.setToolTip(
            "Publish a reset so every emulator returns to its safe demo state."
        )
        self.reset_button.clicked.connect(self._reset_demo)
        layout.addWidget(self.reset_button)
        self.setCentralWidget(central)
        self.setStyleSheet(STYLESHEET)

        for component in self._components:
            component.start()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh)
        self.refresh_timer.start(self.REFRESH_INTERVAL_MS)
        self._refresh()

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title = QLabel("EMULATOR CONSOLE")
        title.setObjectName("appTitle")
        subtitle = QLabel(
            f"Four IoT emulators publishing to coldchain/{self.config.shipment.id}"
        )
        subtitle.setObjectName("subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        layout.addLayout(title_block)
        layout.addStretch()
        self.connection_pill = StatusPill("MQTT CONNECTING", Tone.UNKNOWN)
        layout.addWidget(self.connection_pill)
        return layout

    def _build_dht_group(self) -> QGroupBox:
        group = QGroupBox("A — DHT Sensor Emulator (publisher)")
        layout = QVBoxLayout(group)
        readings = QHBoxLayout()
        readings.setSpacing(10)
        self.temperature_card = StatusCard(
            "Temperature", detail="Published every "
            f"{self.config.emulation.publish_interval_seconds:.0f} s"
        )
        self.humidity_card = StatusCard("Humidity", detail="Published with temperature")
        readings.addWidget(self.temperature_card)
        readings.addWidget(self.humidity_card)
        layout.addLayout(readings)
        self.override_pill = StatusPill("OVERRIDE OFF", Tone.IDLE)
        layout.addWidget(self.override_pill)
        return group

    def _build_door_group(self) -> QGroupBox:
        group = QGroupBox("B — Door Button Emulator (actuator)")
        layout = QVBoxLayout(group)
        self.door_card = StatusCard("Door state", detail="Published only on change")
        self.door_button = QPushButton("OPEN DOOR")
        self.door_button.setToolTip("Toggle the door and publish the retained state.")
        self.door_button.clicked.connect(self.door.toggle)
        layout.addWidget(self.door_card)
        layout.addWidget(self.door_button)
        return group

    def _build_knob_group(self) -> QGroupBox:
        emulation = self.config.emulation
        group = QGroupBox("C — Temperature Knob Emulator (actuator)")
        layout = QVBoxLayout(group)
        self.knob_label = QLabel(f"{emulation.initial_temperature_c:.1f} °C")
        self.knob_label.setObjectName("cardValue")
        caption = QLabel("TARGET TEMPERATURE")
        caption.setObjectName("cardTitle")
        note = QLabel("Sends an override to the DHT emulator, never a sensor reading.")
        note.setObjectName("cardDetail")
        note.setWordWrap(True)

        self.knob_slider = QSlider(Qt.Orientation.Horizontal)
        self.knob_slider.setRange(
            round(emulation.temperature_min_c * 10),
            round(emulation.temperature_max_c * 10),
        )
        self.knob_slider.setValue(round(emulation.initial_temperature_c * 10))
        self.knob_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.knob_slider.setTickInterval(50)
        self.knob_slider.valueChanged.connect(
            lambda value: self.knob_label.setText(f"{value / 10:.1f} °C")
        )

        buttons = QHBoxLayout()
        apply_button = QPushButton("APPLY OVERRIDE")
        apply_button.clicked.connect(
            lambda: self.knob.set_temperature(self.knob_slider.value() / 10)
        )
        release_button = QPushButton("RELEASE")
        release_button.setToolTip("Return the DHT emulator to automatic simulation.")
        release_button.clicked.connect(self.knob.release_override)
        buttons.addWidget(apply_button)
        buttons.addWidget(release_button)

        layout.addWidget(caption)
        layout.addWidget(self.knob_label)
        layout.addWidget(self.knob_slider)
        layout.addLayout(buttons)
        layout.addWidget(note)
        return group

    def _build_relay_group(self) -> QGroupBox:
        group = QGroupBox("D — Cooling Relay Emulator (actuator)")
        layout = QVBoxLayout(group)
        self.relay_card = StatusCard(
            "Cooling relay", detail="Changes only after an MQTT command"
        )
        note = QLabel(
            "The relay confirms its own state, so the dashboard always shows the "
            "actual hardware state rather than the requested one."
        )
        note.setObjectName("cardDetail")
        note.setWordWrap(True)
        layout.addWidget(self.relay_card)
        layout.addWidget(note)
        return group

    def _refresh(self) -> None:
        snapshot = self.dht.snapshot()
        self.temperature_card.update_reading(
            value=f"{snapshot.temperature_c:.1f} °C",
            badge="SIMULATED" if not snapshot.override_enabled else "OVERRIDDEN",
            tone=Tone.INFO if snapshot.override_enabled else Tone.NORMAL,
        )
        self.humidity_card.update_reading(
            value=f"{snapshot.humidity_percent:.1f} %",
            badge="SIMULATED",
            tone=Tone.NORMAL,
        )
        if snapshot.override_enabled and snapshot.override_target_c is not None:
            self.override_pill.update_state(
                f"OVERRIDE {snapshot.override_target_c:.1f} °C", Tone.INFO
            )
        else:
            self.override_pill.update_state("OVERRIDE OFF", Tone.IDLE)

        door_open = self.door.state == DoorState.OPEN
        self.door_card.update_reading(
            value=str(self.door.state),
            badge="ATTENTION" if door_open else "NORMAL",
            tone=tone_for_status(str(self.door.state)),
        )
        self.door_button.setText("CLOSE DOOR" if door_open else "OPEN DOOR")

        relay_on = self.relay.state == RelayState.ON
        self.relay_card.update_reading(
            value=str(self.relay.state),
            badge="ACTIVE" if relay_on else "IDLE",
            tone=tone_for_status(str(self.relay.state)),
        )

        connected = sum(component.is_connected for component in self._components)
        self.connection_pill.update_state(
            f"{connected}/4 EMULATORS ONLINE",
            Tone.NORMAL if connected == len(self._components) else Tone.WARNING,
        )

    def _reset_demo(self) -> None:
        self.knob_slider.setValue(
            round(self.config.emulation.initial_temperature_c * 10)
        )
        self.knob.reset_demo()

    def closeEvent(self, event) -> None:
        for component in reversed(self._components):
            component.stop()
        event.accept()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    application = QApplication(sys.argv)
    window = EmulatorConsole()
    window.show()
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())
