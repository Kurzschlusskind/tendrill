"""
Tendrill Configuration

Zentrale Konfiguration mit pydantic-settings.
Unterstützt Environment Variables und .env Dateien.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Datenbank-Konfiguration."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: PostgresDsn = Field(
        default="postgresql+asyncpg://tendrill:tendrill_secret@localhost:5432/tendrill",
        description="PostgreSQL Connection URL",
    )
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout: int = Field(default=30, ge=1)
    echo: bool = Field(default=False, description="SQL Query Logging")


class MQTTSettings(BaseSettings):
    """MQTT Broker Konfiguration."""

    model_config = SettingsConfigDict(env_prefix="MQTT_")

    host: str = Field(default="localhost")
    port: int = Field(default=1883, ge=1, le=65535)
    user: str | None = Field(default=None)
    password: str | None = Field(default=None)
    client_id: str = Field(default="tendrill-backend")
    keepalive: int = Field(default=60, ge=10, le=3600)
    reconnect_interval: int = Field(default=5, ge=1, le=60)

    # Topic Configuration
    topic_prefix: str = Field(default="tendrill")

    @property
    def sensor_topic(self) -> str:
        """MQTT Topic für Sensordaten."""
        return f"{self.topic_prefix}/sensors/+/data"

    @property
    def actuator_topic(self) -> str:
        """MQTT Topic für Aktor-Befehle."""
        return f"{self.topic_prefix}/actuators/+/command"


class RedisSettings(BaseSettings):
    """Redis Konfiguration (für Caching und WebSocket Broadcasting)."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = Field(default="localhost")
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0, le=15)
    password: str | None = Field(default=None)

    @property
    def url(self) -> str:
        """Redis Connection URL."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class LoggingSettings(BaseSettings):
    """Logging-Konfiguration."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    format: Literal["json", "console"] = Field(
        default="console",
        description="Log output format"
    )
    show_timestamps: bool = Field(default=True)


class AlertSettings(BaseSettings):
    """Alert-Konfiguration."""

    model_config = SettingsConfigDict(env_prefix="ALERT_")

    # Verzögerung bevor ein Alert ausgelöst wird (Sekunden)
    debounce_seconds: int = Field(default=60, ge=0)

    # Wiederholung von Alerts (Minuten)
    repeat_interval_minutes: int = Field(default=30, ge=1)

    # Maximale Anzahl ungelöster Alerts pro Zone
    max_unresolved_per_zone: int = Field(default=100, ge=10)


class Settings(BaseSettings):
    """
    Haupt-Konfiguration für Tendrill.

    Lädt Einstellungen aus:
    1. Environment Variables (höchste Priorität)
    2. .env Datei
    3. Default Values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TENDRILL_",
        extra="ignore",
    )

    # App Metadata
    app_name: str = Field(default="Tendrill")
    version: str = Field(default="0.1.0")
    env: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    debug: bool = Field(default=False)

    # API Settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = Field(default="/api/v1")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://localhost:8888", "http://127.0.0.1:8888", "null", "*"]
    )

    # Security
    secret_key: str = Field(
        default="CHANGE-ME-IN-PRODUCTION-use-openssl-rand-hex-32",
        min_length=32,
    )

    # Data Directory
    data_dir: Path = Field(default=Path("data"))

    # Sub-Settings (geladen aus eigenen Env-Prefixes)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    mqtt: MQTTSettings = Field(default_factory=MQTTSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    alerts: AlertSettings = Field(default_factory=AlertSettings)

    @field_validator("data_dir", mode="before")
    @classmethod
    def resolve_data_dir(cls, v: str | Path) -> Path:
        """Konvertiert data_dir zu absolutem Pfad."""
        path = Path(v)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    @property
    def is_development(self) -> bool:
        """Prüft ob Development-Modus aktiv ist."""
        return self.env == "development"

    @property
    def is_production(self) -> bool:
        """Prüft ob Production-Modus aktiv ist."""
        return self.env == "production"

    @property
    def knowledge_dir(self) -> Path:
        """Pfad zum Knowledge-Verzeichnis."""
        return self.data_dir / "knowledge"


@lru_cache
def get_settings() -> Settings:
    """
    Gibt die gecachte Settings-Instanz zurück.

    Singleton-Pattern mit lru_cache für Performance.
    """
    return Settings()


# Convenience exports
settings = get_settings()
