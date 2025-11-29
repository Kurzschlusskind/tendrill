"""
Tendrill Actuator Devices

Definitionen und Interfaces für Aktoren.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActuatorType(str, Enum):
    """Typen von Aktoren."""

    # Klimasteuerung
    EXHAUST_FAN = "exhaust_fan"  # Abluft
    INTAKE_FAN = "intake_fan"  # Zuluft
    CIRCULATION_FAN = "circulation_fan"  # Umluft
    HEATER = "heater"  # Heizung
    COOLER = "cooler"  # Kühlung
    HUMIDIFIER = "humidifier"  # Befeuchter
    DEHUMIDIFIER = "dehumidifier"  # Entfeuchter

    # Beleuchtung
    LIGHT_MAIN = "light_main"  # Hauptlicht
    LIGHT_SUPPLEMENTAL = "light_supplemental"  # Zusatzlicht
    LIGHT_UV = "light_uv"  # UV-Licht

    # Bewässerung
    WATER_PUMP = "water_pump"  # Wasserpumpe
    NUTRIENT_PUMP = "nutrient_pump"  # Nährstoffpumpe
    PH_UP_PUMP = "ph_up_pump"  # pH+ Pumpe
    PH_DOWN_PUMP = "ph_down_pump"  # pH- Pumpe
    DRAIN_VALVE = "drain_valve"  # Ablassventil

    # CO2
    CO2_VALVE = "co2_valve"  # CO2 Ventil
    CO2_GENERATOR = "co2_generator"  # CO2 Generator

    # Sonstige
    RELAY = "relay"  # Generisches Relais


class ActuatorState(str, Enum):
    """Mögliche Zustände eines Aktors."""

    OFF = "off"
    ON = "on"
    AUTO = "auto"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class ActuatorCapabilities:
    """Fähigkeiten eines Aktors."""

    # On/Off Steuerung
    can_switch: bool = True

    # Dimming / Variable Geschwindigkeit
    can_dim: bool = False
    dim_min: int = 0
    dim_max: int = 100

    # Timer-Funktionen
    can_schedule: bool = True

    # Feedback vom Gerät
    has_feedback: bool = False


@dataclass
class ActuatorDevice:
    """
    Repräsentation eines Aktor-Geräts.

    Beispiel:
        device = ActuatorDevice(
            device_id="exhaust-01",
            name="Abluftventilator",
            actuator_type=ActuatorType.EXHAUST_FAN,
            mqtt_topic="tendrill/actuators/exhaust-01/command",
            capabilities=ActuatorCapabilities(can_dim=True),
        )
    """

    device_id: str
    name: str
    actuator_type: ActuatorType
    mqtt_topic: str
    capabilities: ActuatorCapabilities = field(default_factory=ActuatorCapabilities)
    state: ActuatorState = ActuatorState.UNKNOWN
    current_value: int = 0  # 0-100 für dimmbare Geräte
    last_command: dict | None = None
    config: dict = field(default_factory=dict)

    def get_command_payload(
        self,
        command: str,
        value: int | None = None,
        params: dict | None = None,
    ) -> dict:
        """
        Erstellt ein MQTT Command Payload.

        Args:
            command: Befehlsname (on, off, set, dim, etc.)
            value: Wert für dimmbare Geräte (0-100)
            params: Zusätzliche Parameter

        Returns:
            Dict für MQTT Publish
        """
        payload = {
            "device_id": self.device_id,
            "command": command,
        }

        if value is not None:
            if self.capabilities.can_dim:
                # Wert auf erlaubten Bereich begrenzen
                value = max(self.capabilities.dim_min, min(value, self.capabilities.dim_max))
            payload["value"] = value

        if params:
            payload["params"] = params

        return payload


# =============================================================================
# Vordefinierte Geräte-Templates
# =============================================================================

DEVICE_TEMPLATES: dict[ActuatorType, ActuatorCapabilities] = {
    ActuatorType.EXHAUST_FAN: ActuatorCapabilities(
        can_dim=True,
        dim_min=0,
        dim_max=100,
    ),
    ActuatorType.INTAKE_FAN: ActuatorCapabilities(
        can_dim=True,
        dim_min=0,
        dim_max=100,
    ),
    ActuatorType.CIRCULATION_FAN: ActuatorCapabilities(
        can_dim=True,
        dim_min=0,
        dim_max=100,
    ),
    ActuatorType.LIGHT_MAIN: ActuatorCapabilities(
        can_dim=True,
        dim_min=0,
        dim_max=100,
    ),
    ActuatorType.HUMIDIFIER: ActuatorCapabilities(
        can_dim=False,
    ),
    ActuatorType.DEHUMIDIFIER: ActuatorCapabilities(
        can_dim=False,
    ),
    ActuatorType.WATER_PUMP: ActuatorCapabilities(
        can_dim=False,
    ),
    ActuatorType.CO2_VALVE: ActuatorCapabilities(
        can_dim=False,
    ),
    ActuatorType.RELAY: ActuatorCapabilities(
        can_dim=False,
    ),
}


def create_device(
    device_id: str,
    name: str,
    actuator_type: ActuatorType,
    mqtt_topic: str | None = None,
) -> ActuatorDevice:
    """
    Factory-Funktion zum Erstellen eines Aktor-Geräts.

    Verwendet Templates für Standard-Capabilities.
    """
    if mqtt_topic is None:
        mqtt_topic = f"tendrill/actuators/{device_id}/command"

    capabilities = DEVICE_TEMPLATES.get(
        actuator_type,
        ActuatorCapabilities(),
    )

    return ActuatorDevice(
        device_id=device_id,
        name=name,
        actuator_type=actuator_type,
        mqtt_topic=mqtt_topic,
        capabilities=capabilities,
    )
