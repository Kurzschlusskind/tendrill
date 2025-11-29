"""
Tendrill MQTT Client

Threaded MQTT Client mit paho-mqtt für Windows-Kompatibilität.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import paho.mqtt.client as mqtt
import structlog

from tendrill.config import get_settings
from tendrill.sensors.models import ESP32SensorReading, SensorPayload

logger = structlog.get_logger(__name__)

# Type für Message Handler Callbacks
MessageHandler = Callable[[str, dict], Coroutine[Any, Any, None]]


class MQTTClient:
    """
    Threaded MQTT Client für Tendrill.

    Nutzt paho-mqtt mit loop_start() für Windows-Kompatibilität.
    """

    def __init__(self) -> None:
        self.settings = get_settings().mqtt
        self._client: mqtt.Client | None = None
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = threading.Event()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback bei Verbindung."""
        if reason_code == 0:
            logger.info("mqtt_connected", host=self.settings.host, port=self.settings.port)
            self._connected.set()
            # Subscribe auf Topics
            client.subscribe(self.settings.sensor_topic)
            logger.info("mqtt_subscribed", topic=self.settings.sensor_topic)
            status_topic = f"{self.settings.topic_prefix}/sensors/+/status"
            client.subscribe(status_topic)
        else:
            logger.error("mqtt_connection_failed", reason=reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback bei Trennung."""
        logger.warning("mqtt_disconnected", reason=reason_code)
        self._connected.clear()

    def _on_message(self, client, userdata, message):
        """Callback für eingehende Nachrichten."""
        topic = message.topic
        try:
            payload = message.payload.decode("utf-8")
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("mqtt_invalid_message", topic=topic, error=str(e))
            return

        logger.debug("mqtt_message", topic=topic)

        # Handler im asyncio Loop aufrufen
        if self._loop:
            for pattern, handlers in self._handlers.items():
                if self._topic_matches(topic, pattern):
                    for handler in handlers:
                        asyncio.run_coroutine_threadsafe(
                            self._safe_handler(handler, topic, data),
                            self._loop
                        )

    async def _safe_handler(self, handler: MessageHandler, topic: str, data: dict):
        """Wrapper für sicheren Handler-Aufruf."""
        try:
            await handler(topic, data)
        except Exception as e:
            logger.error("mqtt_handler_error", topic=topic, error=str(e))

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Prüft ob Topic auf Pattern passt."""
        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")

        if len(pattern_parts) > len(topic_parts):
            return False

        for i, part in enumerate(pattern_parts):
            if part == "#":
                return True
            if part == "+":
                continue
            if i >= len(topic_parts) or part != topic_parts[i]:
                return False

        return len(topic_parts) == len(pattern_parts)

    async def start(self) -> None:
        """Startet den MQTT Client."""
        self._loop = asyncio.get_running_loop()
        self._running = True

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        # Auth nur wenn User gesetzt
        if self.settings.user:
            self._client.username_pw_set(self.settings.user, self.settings.password)

        try:
            self._client.connect(self.settings.host, self.settings.port, self.settings.keepalive)
            self._client.loop_start()
            logger.info("mqtt_client_started")
        except Exception as e:
            logger.error("mqtt_start_error", error=str(e))
            raise

    async def stop(self) -> None:
        """Stoppt den MQTT Client."""
        self._running = False
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        logger.info("mqtt_client_stopped")

    def on_message(self, topic_pattern: str, handler: MessageHandler) -> None:
        """Registriert einen Message Handler."""
        if topic_pattern not in self._handlers:
            self._handlers[topic_pattern] = []
        self._handlers[topic_pattern].append(handler)

    async def publish(self, topic: str, payload: dict | str, qos: int = 1, retain: bool = False) -> None:
        """Publiziert eine Nachricht."""
        if not self._client or not self._connected.is_set():
            raise RuntimeError("MQTT Client not connected")

        if isinstance(payload, dict):
            payload = json.dumps(payload)

        self._client.publish(topic, payload, qos=qos, retain=retain)
        logger.debug("mqtt_published", topic=topic)

    async def send_actuator_command(self, device_id: str, command: str, params: dict | None = None) -> None:
        """Sendet Befehl an Aktor."""
        topic = f"{self.settings.topic_prefix}/actuators/{device_id}/command"
        payload = {"command": command, "params": params or {}}
        await self.publish(topic, payload)

    @staticmethod
    def parse_sensor_payload(data: dict) -> SensorPayload:
        """Parst Sensor Payload."""
        if "d" in data and "r" in data:
            compact = ESP32SensorReading.model_validate(data)
            return compact.to_sensor_payload()
        return SensorPayload.model_validate(data)


# Singleton
_mqtt_client: MQTTClient | None = None


def get_mqtt_client() -> MQTTClient:
    """Gibt Singleton MQTT Client zurück."""
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = MQTTClient()
    return _mqtt_client
