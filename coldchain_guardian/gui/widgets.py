"""Reusable presentation widgets shared by the dashboard and emulator console."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from coldchain_guardian.gui.theme import Tone, apply_tone, repolish


class StatusPill(QLabel):
    """Compact rounded label used for header status such as MQTT or MODE."""

    def __init__(self, text: str = "", tone: Tone = Tone.UNKNOWN) -> None:
        super().__init__(text)
        self.setObjectName("pill")
        # Without this a pill stretches to fill whatever row it lands in.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        apply_tone(self, tone)

    def update_state(self, text: str, tone: Tone) -> None:
        self.setText(text)
        apply_tone(self, tone)


class StatusCard(QFrame):
    """Title, large reading, tone badge, and a small line of context.

    The badge describes the assessment ("NORMAL", "ATTENTION") rather than
    repeating the reading, so a card never prints the same word twice.
    """

    def __init__(self, title: str, *, detail: str = "") -> None:
        super().__init__()
        self.setObjectName("statusCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("cardTitle")
        self.value_label = QLabel("--")
        self.value_label.setObjectName("cardValue")
        self.badge_label = QLabel("UNKNOWN")
        self.badge_label.setObjectName("cardBadge")
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("cardDetail")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.badge_label)
        layout.addWidget(self.detail_label)

        apply_tone(self, Tone.UNKNOWN)
        apply_tone(self.badge_label, Tone.UNKNOWN)

    def update_reading(
        self,
        *,
        value: str,
        badge: str,
        tone: Tone,
        detail: str | None = None,
    ) -> None:
        self.value_label.setText(value)
        self.badge_label.setText(badge)
        apply_tone(self, tone)
        apply_tone(self.badge_label, tone)
        if detail is not None:
            self.detail_label.setText(detail)


class AlertBanner(QFrame):
    """One high-visibility line describing the worst unresolved condition.

    Alarms pulse because a static red border is easy to miss on a recording;
    every other tone stays still so the motion keeps its meaning.
    """

    PULSE_INTERVAL_MS = 700

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("alertBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(14)

        self.severity_label = QLabel()
        self.severity_label.setObjectName("bannerSeverity")
        self.headline_label = QLabel()
        self.headline_label.setObjectName("bannerHeadline")
        self.detail_label = QLabel()
        self.detail_label.setObjectName("bannerDetail")

        layout.addWidget(self.severity_label)
        layout.addWidget(self.headline_label, stretch=1)
        layout.addWidget(self.detail_label)

        self._pulse_active = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(self.PULSE_INTERVAL_MS)
        self._pulse_timer.timeout.connect(self._toggle_pulse)

        self.show_normal()

    def show_normal(self) -> None:
        self.show_state(
            tone=Tone.NORMAL,
            severity="NORMAL",
            headline="All systems normal",
            detail="No unacknowledged warnings",
        )

    def show_state(
        self, *, tone: Tone, severity: str, headline: str, detail: str
    ) -> None:
        self.severity_label.setText(severity)
        self.headline_label.setText(headline)
        self.detail_label.setText(detail)
        apply_tone(self, tone)
        apply_tone(self.severity_label, tone)

        if tone == Tone.ALARM:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
            self._set_pulse(False)

    def _toggle_pulse(self) -> None:
        self._set_pulse(not self._pulse_active)

    def _set_pulse(self, active: bool) -> None:
        self._pulse_active = active
        self.setProperty("pulse", "true" if active else "false")
        repolish(self)
