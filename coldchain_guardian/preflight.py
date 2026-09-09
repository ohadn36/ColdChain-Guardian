"""Local runtime checks used before launching the demonstration."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import shutil
import socket

from coldchain_guardian.config import AppConfig


REQUIRED_MODULES = {
    "yaml": "PyYAML",
    "paho.mqtt.client": "paho-mqtt",
    "PySide6": "PySide6",
    "pyqtgraph": "pyqtgraph",
}


@dataclass(frozen=True)
class PreflightReport:
    missing_packages: tuple[str, ...]
    broker_reachable: bool
    mosquitto_executable: str | None

    @property
    def can_launch(self) -> bool:
        return not self.missing_packages and (
            self.broker_reachable or self.mosquitto_executable is not None
        )


def check_dependencies() -> tuple[str, ...]:
    missing = []
    for module, package in REQUIRED_MODULES.items():
        try:
            available = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            available = False
        if not available:
            missing.append(package)
    return tuple(missing)


def broker_is_reachable(host: str, port: int, *, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_preflight(config: AppConfig) -> PreflightReport:
    return PreflightReport(
        missing_packages=check_dependencies(),
        broker_reachable=broker_is_reachable(config.mqtt.host, config.mqtt.port),
        mosquitto_executable=shutil.which("mosquitto"),
    )
