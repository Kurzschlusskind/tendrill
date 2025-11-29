"""
Tendrill Actuator Controller

Steuerung und Verwaltung von Aktoren.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from tendrill.actuators.devices import (
    ActuatorDevice,
    ActuatorState,
    ActuatorType,
    create_device,
)
from tendrill.sensors.mqtt import get_mqtt_client

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class ActuatorController:
    """
    Controller für Aktor-Steuerung.

    Verwaltet registrierte Aktoren und sendet Befehle via MQTT.
    """

    def __init__(self) -> None:
        self._devices: dict[str, ActuatorDevice] = {}
        self._mqtt = get_mqtt_client()

    # =========================================================================
    # Device Management
    # =========================================================================

    def register_device(self, device: ActuatorDevice) -> None:
        """Registriert ein Aktor-Gerät."""
        self._devices[device.device_id] = device
        logger.info(
            "actuator_registered",
            device_id=device.device_id,
            type=device.actuator_type.value,
        )

    def unregister_device(self, device_id: str) -> bool:
        """Entfernt ein Aktor-Gerät."""
        if device_id in self._devices:
            del self._devices[device_id]
            logger.info("actuator_unregistered", device_id=device_id)
            return True
        return False

    def get_device(self, device_id: str) -> ActuatorDevice | None:
        """Holt ein Gerät by ID."""
        return self._devices.get(device_id)

    def get_devices(
        self,
        actuator_type: ActuatorType | None = None,
    ) -> list[ActuatorDevice]:
        """Holt alle Geräte, optional gefiltert nach Typ."""
        devices = list(self._devices.values())
        if actuator_type:
            devices = [d for d in devices if d.actuator_type == actuator_type]
        return devices

    # =========================================================================
    # Commands
    # =========================================================================

    async def turn_on(
        self,
        device_id: str,
        value: int = 100,
    ) -> bool:
        """
        Schaltet einen Aktor ein.

        Args:
            device_id: Device ID
            value: Wert für dimmbare Geräte (0-100)
        """
        device = self.get_device(device_id)
        if not device:
            logger.warning("actuator_not_found", device_id=device_id)
            return False

        payload = device.get_command_payload("on", value=value)
        await self._mqtt.publish(device.mqtt_topic, payload)

        device.state = ActuatorState.ON
        device.current_value = value
        device.last_command = payload

        logger.info(
            "actuator_turned_on",
            device_id=device_id,
            value=value,
        )
        return True

    async def turn_off(self, device_id: str) -> bool:
        """Schaltet einen Aktor aus."""
        device = self.get_device(device_id)
        if not device:
            logger.warning("actuator_not_found", device_id=device_id)
            return False

        payload = device.get_command_payload("off")
        await self._mqtt.publish(device.mqtt_topic, payload)

        device.state = ActuatorState.OFF
        device.current_value = 0
        device.last_command = payload

        logger.info("actuator_turned_off", device_id=device_id)
        return True

    async def set_value(
        self,
        device_id: str,
        value: int,
    ) -> bool:
        """
        Setzt den Wert eines dimmbaren Aktors.

        Args:
            device_id: Device ID
            value: Wert (0-100)
        """
        device = self.get_device(device_id)
        if not device:
            logger.warning("actuator_not_found", device_id=device_id)
            return False

        if not device.capabilities.can_dim:
            logger.warning("actuator_not_dimmable", device_id=device_id)
            return False

        payload = device.get_command_payload("set", value=value)
        await self._mqtt.publish(device.mqtt_topic, payload)

        device.state = ActuatorState.ON if value > 0 else ActuatorState.OFF
        device.current_value = value
        device.last_command = payload

        logger.info(
            "actuator_value_set",
            device_id=device_id,
            value=value,
        )
        return True

    async def toggle(self, device_id: str) -> bool:
        """Schaltet einen Aktor um (on -> off, off -> on)."""
        device = self.get_device(device_id)
        if not device:
            return False

        if device.state == ActuatorState.ON:
            return await self.turn_off(device_id)
        else:
            return await self.turn_on(device_id)

    # =========================================================================
    # Group Commands
    # =========================================================================

    async def turn_off_all(
        self,
        actuator_type: ActuatorType | None = None,
    ) -> int:
        """
        Schaltet alle Aktoren aus.

        Args:
            actuator_type: Optional nur bestimmten Typ

        Returns:
            Anzahl ausgeschalteter Geräte
        """
        devices = self.get_devices(actuator_type=actuator_type)
        count = 0

        for device in devices:
            if await self.turn_off(device.device_id):
                count += 1

        logger.info(
            "actuators_turned_off",
            count=count,
            type=actuator_type.value if actuator_type else "all",
        )
        return count

    async def set_fan_speed(self, speed: int) -> int:
        """
        Setzt die Geschwindigkeit aller Ventilatoren.

        Args:
            speed: Geschwindigkeit 0-100

        Returns:
            Anzahl geänderter Geräte
        """
        fan_types = [
            ActuatorType.EXHAUST_FAN,
            ActuatorType.INTAKE_FAN,
            ActuatorType.CIRCULATION_FAN,
        ]

        count = 0
        for fan_type in fan_types:
            for device in self.get_devices(actuator_type=fan_type):
                if await self.set_value(device.device_id, speed):
                    count += 1

        return count

    async def set_light_level(self, level: int) -> int:
        """
        Setzt die Helligkeit aller Lichter.

        Args:
            level: Helligkeit 0-100

        Returns:
            Anzahl geänderter Geräte
        """
        light_types = [
            ActuatorType.LIGHT_MAIN,
            ActuatorType.LIGHT_SUPPLEMENTAL,
        ]

        count = 0
        for light_type in light_types:
            for device in self.get_devices(actuator_type=light_type):
                if await self.set_value(device.device_id, level):
                    count += 1

        return count

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> dict:
        """Holt Status aller Aktoren."""
        return {
            device_id: {
                "name": device.name,
                "type": device.actuator_type.value,
                "state": device.state.value,
                "value": device.current_value,
            }
            for device_id, device in self._devices.items()
        }

    def get_device_status(self, device_id: str) -> dict | None:
        """Holt Status eines einzelnen Aktors."""
        device = self.get_device(device_id)
        if not device:
            return None

        return {
            "device_id": device.device_id,
            "name": device.name,
            "type": device.actuator_type.value,
            "state": device.state.value,
            "value": device.current_value,
            "capabilities": {
                "can_switch": device.capabilities.can_switch,
                "can_dim": device.capabilities.can_dim,
                "dim_range": [device.capabilities.dim_min, device.capabilities.dim_max]
                if device.capabilities.can_dim
                else None,
            },
            "last_command": device.last_command,
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_controller: ActuatorController | None = None


def get_actuator_controller() -> ActuatorController:
    """Gibt die Singleton Controller Instanz zurück."""
    global _controller
    if _controller is None:
        _controller = ActuatorController()
    return _controller
