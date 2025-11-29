"""
Tendrill Sensor Models

Pydantic Models für MQTT Sensor Payloads.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SensorStatus(str, Enum):
    """Sensor Status."""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    CALIBRATING = "calibrating"


class SensorData(BaseModel):
    """
    Einzelner Sensor-Messwert.

    Wird vom ESP32 gesendet und enthält einen Messwert
    mit Metadaten.
    """

    type: str = Field(..., description="Sensor Typ (temperature, humidity, co2, etc.)")
    value: float = Field(..., description="Messwert")
    unit: str = Field(..., description="Einheit (°C, %, ppm, etc.)")
    quality: int = Field(default=100, ge=0, le=100, description="Qualität 0-100")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validiert und normalisiert den Sensor-Typ."""
        return v.lower().strip()


class SensorPayload(BaseModel):
    """
    MQTT Payload für Sensor-Daten.

    Erwartetes JSON Format vom ESP32:
    {
        "device_id": "esp32-growroom-01",
        "zone_id": "zone-main",
        "timestamp": "2024-01-15T14:30:00Z",  // optional
        "readings": [
            {"type": "temperature", "value": 24.5, "unit": "°C"},
            {"type": "humidity", "value": 65.2, "unit": "%"},
            {"type": "co2", "value": 850, "unit": "ppm"}
        ],
        "status": "online",
        "firmware_version": "1.0.0"  // optional
    }
    """

    device_id: str = Field(..., min_length=1, max_length=100)
    zone_id: str = Field(..., min_length=1, max_length=100)
    readings: list[SensorData] = Field(..., min_length=1)
    timestamp: datetime | None = Field(default=None)
    status: SensorStatus = Field(default=SensorStatus.ONLINE)
    firmware_version: str | None = Field(default=None)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: str | datetime | None) -> datetime | None:
        """Parst ISO Timestamp String."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        # ISO Format parsen
        return datetime.fromisoformat(v.replace("Z", "+00:00"))

    def get_reading(self, sensor_type: str) -> SensorData | None:
        """Holt ein Reading by Type."""
        for reading in self.readings:
            if reading.type == sensor_type.lower():
                return reading
        return None


class DeviceStatus(BaseModel):
    """
    Device Status Nachricht.

    Wird für Heartbeats und Status-Updates verwendet.
    """

    device_id: str
    status: SensorStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    uptime_seconds: int | None = None
    free_heap: int | None = None
    wifi_rssi: int | None = None
    firmware_version: str | None = None
    ip_address: str | None = None


class SensorConfig(BaseModel):
    """
    Sensor-Konfiguration.

    Kann an den ESP32 gesendet werden um
    Einstellungen zu ändern.
    """

    device_id: str
    reading_interval_seconds: int = Field(default=30, ge=5, le=3600)
    sensors_enabled: list[str] = Field(default_factory=list)
    calibration: dict[str, float] = Field(default_factory=dict)


# =============================================================================
# ESP32 spezifische Formate
# =============================================================================


class ESP32SensorReading(BaseModel):
    """
    Kompaktes Format für ESP32 mit begrenztem RAM.

    Minimales JSON für Bandbreiten-Effizienz:
    {
        "d": "esp01",
        "z": "main",
        "t": 1705329000,
        "r": [
            ["T", 24.5],
            ["H", 65.2],
            ["C", 850]
        ]
    }
    """

    d: str = Field(..., alias="device_id", description="Device ID (kurz)")
    z: str = Field(..., alias="zone_id", description="Zone ID (kurz)")
    t: int | None = Field(default=None, alias="timestamp", description="Unix Timestamp")
    r: list[tuple[str, float]] = Field(..., alias="readings", description="[Type, Value] Paare")

    model_config = {"populate_by_name": True}

    # Mapping von Kurzform zu Langform
    TYPE_MAP: dict[str, tuple[str, str]] = {
        "T": ("temperature", "°C"),
        "H": ("humidity", "%"),
        "C": ("co2", "ppm"),
        "L": ("light_ppfd", "µmol/m²/s"),
        "P": ("ph", "pH"),
        "E": ("ec", "mS/cm"),
        "V": ("vpd", "kPa"),
        "W": ("water_temperature", "°C"),
    }

    def to_sensor_payload(self) -> SensorPayload:
        """Konvertiert zu Standard SensorPayload."""
        readings = []
        for type_short, value in self.r:
            if type_short in self.TYPE_MAP:
                type_long, unit = self.TYPE_MAP[type_short]
            else:
                type_long = type_short.lower()
                unit = ""

            readings.append(SensorData(type=type_long, value=value, unit=unit))

        timestamp = None
        if self.t:
            timestamp = datetime.fromtimestamp(self.t)

        return SensorPayload(
            device_id=self.d,
            zone_id=self.z,
            timestamp=timestamp,
            readings=readings,
        )
