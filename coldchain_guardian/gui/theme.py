"""Shared visual language for every ColdChain Guardian desktop window."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtWidgets import QWidget


class Tone(StrEnum):
    """Semantic severity role shared by cards, pills, banners, and tables."""

    NORMAL = "normal"
    INFO = "info"
    WARNING = "warning"
    ALARM = "alarm"
    IDLE = "idle"
    UNKNOWN = "unknown"


BACKGROUND = "#0f172a"
SURFACE = "#1e293b"
SURFACE_DEEP = "#111827"
BORDER = "#334155"
TEXT = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
ACCENT = "#38bdf8"

_TONE_RGB: dict[Tone, tuple[int, int, int]] = {
    Tone.NORMAL: (34, 197, 94),
    Tone.INFO: (56, 189, 248),
    Tone.WARNING: (245, 158, 11),
    Tone.ALARM: (239, 68, 68),
    Tone.IDLE: (148, 163, 184),
    Tone.UNKNOWN: (100, 116, 139),
}

# Every status string the Data Manager can place in a snapshot or alert.
_STATUS_TONES: dict[str, Tone] = {
    "NORMAL": Tone.NORMAL,
    "CLOSED": Tone.NORMAL,
    "INFO": Tone.INFO,
    "ON": Tone.INFO,
    "WARNING": Tone.WARNING,
    "WARNING_LOW": Tone.WARNING,
    "WARNING_HIGH": Tone.WARNING,
    "OPEN": Tone.WARNING,
    "ALARM": Tone.ALARM,
    "ALARM_HIGH": Tone.ALARM,
    "OFF": Tone.IDLE,
    "UNKNOWN": Tone.UNKNOWN,
}


def tone_for_status(status: str) -> Tone:
    """Map a manager status, door/relay state, or severity onto a display tone."""

    return _STATUS_TONES.get(status.upper(), Tone.UNKNOWN)


def tone_rgb(tone: Tone) -> tuple[int, int, int]:
    """Return the red, green, and blue channels for a tone."""

    return _TONE_RGB[tone]


def tone_hex(tone: Tone) -> str:
    """Return the tone as a CSS hex colour."""

    red, green, blue = _TONE_RGB[tone]
    return f"#{red:02x}{green:02x}{blue:02x}"


def tone_rgba(tone: Tone, alpha: float) -> str:
    """Return the tone as a CSS rgba colour with the requested opacity."""

    red, green, blue = _TONE_RGB[tone]
    return f"rgba({red}, {green}, {blue}, {alpha})"


def repolish(widget: QWidget) -> None:
    """Re-evaluate the stylesheet after a dynamic property changed."""

    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def apply_tone(widget: QWidget, tone: Tone) -> None:
    """Tag a widget with a tone so the global stylesheet can colour it."""

    widget.setProperty("tone", str(tone))
    repolish(widget)


def _tone_rules() -> str:
    """Generate the per-tone colour rules instead of repeating them by hand."""

    rules: list[str] = []
    for tone in Tone:
        color = tone_hex(tone)
        rules.append(
            f'QFrame#statusCard[tone="{tone}"] {{ border-left-color: {color}; }}\n'
            f'QLabel#cardBadge[tone="{tone}"] {{ color: {color}; }}\n'
            f'QLabel#pill[tone="{tone}"] {{ color: {color}; '
            f"border-color: {tone_rgba(tone, 0.55)}; "
            f"background: {tone_rgba(tone, 0.12)}; }}\n"
            f'QFrame#alertBanner[tone="{tone}"] {{ border-color: {color}; '
            f"background: {tone_rgba(tone, 0.16)}; }}\n"
            f'QLabel#bannerSeverity[tone="{tone}"] {{ color: {color}; }}'
        )
    # The pulse only applies to alarms, where the extra motion is meaningful.
    rules.append(
        'QFrame#alertBanner[tone="alarm"][pulse="true"] {'
        f" background: {tone_rgba(Tone.ALARM, 0.38)}; }}"
    )
    return "\n".join(rules)


STYLESHEET = f"""
QWidget {{ background: {BACKGROUND}; color: {TEXT}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QToolTip {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 6px; border-radius: 4px;
}}

QLabel#appTitle {{ color: {ACCENT}; font-size: 24px; font-weight: 800; }}
QLabel#subtitle {{ color: {TEXT_MUTED}; font-size: 13px; }}
QLabel#sectionTitle {{ color: {ACCENT}; font-size: 17px; font-weight: 700; }}

QLabel#pill {{
    border: 1px solid {BORDER}; border-radius: 11px;
    padding: 4px 12px; font-size: 11px; font-weight: 700;
}}

QFrame#statusCard {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-left: 6px solid {tone_hex(Tone.UNKNOWN)};
    border-radius: 10px; padding: 12px;
}}
QLabel#cardTitle {{
    color: {TEXT_MUTED}; font-size: 11px; font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#cardValue {{ color: #f8fafc; font-size: 30px; font-weight: 800; }}
QLabel#cardBadge {{ font-size: 12px; font-weight: 800; letter-spacing: 1px; }}
QLabel#cardDetail {{ color: {TEXT_MUTED}; font-size: 11px; }}

QFrame#alertBanner {{
    border: 2px solid {BORDER}; border-radius: 10px; padding: 10px 14px;
}}
QLabel#bannerSeverity {{ font-size: 15px; font-weight: 800; letter-spacing: 1px; }}
QLabel#bannerHeadline {{ color: #f8fafc; font-size: 17px; font-weight: 700; }}
QLabel#bannerDetail {{ color: {TEXT_MUTED}; font-size: 12px; }}

QGroupBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
    margin-top: 14px; padding: 14px; font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {TEXT_MUTED};
}}

QPushButton {{
    background: #0369a1; border: none; border-radius: 6px;
    padding: 9px 14px; font-weight: 700;
}}
QPushButton:hover {{ background: #0284c7; }}
QPushButton:pressed {{ background: #075985; }}
QPushButton:disabled {{ background: {BORDER}; color: #64748b; }}
QPushButton#resetButton {{ background: #b45309; }}
QPushButton#resetButton:hover {{ background: #d97706; }}

QRadioButton {{ background: transparent; padding: 5px 0; font-weight: 700; }}
QRadioButton::indicator {{ width: 15px; height: 15px; }}

QTableWidget {{
    background: {SURFACE_DEEP}; gridline-color: {BORDER};
    border: 1px solid {BORDER}; border-radius: 6px;
}}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:selected {{ background: #0369a1; color: #f8fafc; }}
QHeaderView::section {{
    background: {SURFACE}; padding: 7px; border: none;
    color: {TEXT_MUTED}; font-weight: 700;
}}

QTabBar::tab {{
    background: {SURFACE}; padding: 9px 20px; font-weight: 700;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ background: #0369a1; color: #f8fafc; }}

QScrollBar:vertical {{
    background: {SURFACE_DEEP}; width: 10px; margin: 0; border: none;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #475569; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QSlider::groove:horizontal {{
    height: 6px; background: #475569; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 18px; margin: -7px 0; background: {ACCENT}; border-radius: 9px;
}}
QSlider::sub-page:horizontal {{ background: #0369a1; border-radius: 3px; }}

{_tone_rules()}
"""
