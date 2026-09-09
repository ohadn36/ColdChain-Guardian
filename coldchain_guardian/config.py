"""Application configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class ConfigError(ValueError):
    """Raised when the application configuration is missing or inconsistent."""


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    keepalive_seconds: int
    reconnect_min_delay_seconds: int
    reconnect_max_delay_seconds: int


@dataclass(frozen=True)
class ShipmentConfig:
    id: str


@dataclass(frozen=True)
class DeviceConfig:
    temperature_sensor_id: str
    humidity_sensor_id: str
    door_sensor_id: str
    cooling_relay_id: str


@dataclass(frozen=True)
class EmulationConfig:
    publish_interval_seconds: float
    initial_temperature_c: float
    initial_humidity_percent: float
    temperature_drift_step_c: float
    humidity_drift_step_percent: float
    temperature_min_c: float
    temperature_max_c: float


@dataclass(frozen=True)
class RulesConfig:
    temperature_min_c: float
    temperature_warning_high_c: float
    temperature_alarm_high_c: float
    cooling_off_below_c: float
    humidity_min_percent: float
    humidity_max_percent: float
    door_warning_after_seconds: int
    failure_trend_readings: int


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    data_manager_path: Path


@dataclass(frozen=True)
class GuiConfig:
    chart_history_points: int
    history_row_limit: int


@dataclass(frozen=True)
class AppConfig:
    mqtt: MqttConfig
    shipment: ShipmentConfig
    devices: DeviceConfig
    emulation: EmulationConfig
    rules: RulesConfig
    database: DatabaseConfig
    logging: LoggingConfig
    gui: GuiConfig


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing or invalid configuration section: {name}")
    return value


def _resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _build_config(raw: dict[str, Any]) -> AppConfig:
    try:
        mqtt = MqttConfig(**_section(raw, "mqtt"))
        shipment = ShipmentConfig(**_section(raw, "shipment"))
        devices = DeviceConfig(**_section(raw, "devices"))
        emulation = EmulationConfig(**_section(raw, "emulation"))
        rules = RulesConfig(**_section(raw, "rules"))
        database_raw = _section(raw, "database")
        logging_raw = _section(raw, "logging")
        database = DatabaseConfig(path=_resolve_project_path(database_raw["path"]))
        logging_config = LoggingConfig(
            level=str(logging_raw["level"]).upper(),
            data_manager_path=_resolve_project_path(logging_raw["data_manager_path"]),
        )
        gui = GuiConfig(**_section(raw, "gui"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid configuration value: {exc}") from exc

    config = AppConfig(
        mqtt=mqtt,
        shipment=shipment,
        devices=devices,
        emulation=emulation,
        rules=rules,
        database=database,
        logging=logging_config,
        gui=gui,
    )
    _validate_config(config)
    return config


def _validate_config(config: AppConfig) -> None:
    if not config.mqtt.host.strip():
        raise ConfigError("mqtt.host must not be empty")
    if not 1 <= config.mqtt.port <= 65535:
        raise ConfigError("mqtt.port must be between 1 and 65535")
    if config.mqtt.keepalive_seconds <= 0:
        raise ConfigError("mqtt.keepalive_seconds must be positive")
    if config.mqtt.reconnect_min_delay_seconds <= 0:
        raise ConfigError("mqtt.reconnect_min_delay_seconds must be positive")
    if (
        config.mqtt.reconnect_max_delay_seconds
        < config.mqtt.reconnect_min_delay_seconds
    ):
        raise ConfigError("MQTT reconnect maximum must not be below the minimum")
    if not config.shipment.id.strip():
        raise ConfigError("shipment.id must not be empty")
    if config.emulation.publish_interval_seconds <= 0:
        raise ConfigError("emulation.publish_interval_seconds must be positive")
    if config.emulation.temperature_min_c >= config.emulation.temperature_max_c:
        raise ConfigError("emulation temperature range is invalid")

    rules = config.rules
    if not (
        rules.temperature_min_c
        < rules.temperature_warning_high_c
        < rules.temperature_alarm_high_c
    ):
        raise ConfigError("temperature rule thresholds must be strictly increasing")
    if rules.cooling_off_below_c >= rules.temperature_warning_high_c:
        raise ConfigError("cooling OFF threshold must be below cooling ON threshold")
    if rules.humidity_min_percent >= rules.humidity_max_percent:
        raise ConfigError("humidity rule thresholds are invalid")
    if rules.door_warning_after_seconds <= 0:
        raise ConfigError("door warning duration must be positive")
    if rules.failure_trend_readings < 3:
        raise ConfigError("failure trend requires at least three readings")
    if config.gui.chart_history_points <= 0 or config.gui.history_row_limit <= 0:
        raise ConfigError("GUI history limits must be positive")


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load, normalize, and validate a YAML application configuration."""

    config_path = Path(path)
    try:
        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except OSError as exc:
        raise ConfigError(f"Unable to read configuration: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in configuration: {config_path}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Configuration root must be a mapping")
    return _build_config(raw)

