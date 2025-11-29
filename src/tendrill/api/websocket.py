"""
Tendrill WebSocket API

Real-time Updates für Dashboard-Clients.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class WebSocketMessage(BaseModel):
    """WebSocket Nachricht."""

    type: str
    zone_id: str | None = None
    data: dict


class ConnectionManager:
    """
    WebSocket Connection Manager.

    Verwaltet aktive WebSocket Verbindungen und
    ermöglicht Broadcasting von Updates.
    """

    def __init__(self) -> None:
        # Alle aktiven Verbindungen
        self._connections: set[WebSocket] = set()

        # Zone-spezifische Subscriptions
        self._zone_subscriptions: dict[UUID, set[WebSocket]] = {}

    @property
    def connection_count(self) -> int:
        """Anzahl aktiver Verbindungen."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Akzeptiert eine neue WebSocket Verbindung."""
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("websocket_connected", total=self.connection_count)

    def disconnect(self, websocket: WebSocket) -> None:
        """Entfernt eine WebSocket Verbindung."""
        self._connections.discard(websocket)

        # Aus allen Zone Subscriptions entfernen
        for zone_subs in self._zone_subscriptions.values():
            zone_subs.discard(websocket)

        logger.info("websocket_disconnected", total=self.connection_count)

    def subscribe_zone(self, websocket: WebSocket, zone_id: UUID) -> None:
        """Subscribed einen Client auf Zone Updates."""
        if zone_id not in self._zone_subscriptions:
            self._zone_subscriptions[zone_id] = set()
        self._zone_subscriptions[zone_id].add(websocket)
        logger.debug("websocket_subscribed_zone", zone_id=str(zone_id))

    def unsubscribe_zone(self, websocket: WebSocket, zone_id: UUID) -> None:
        """Entfernt Zone Subscription."""
        if zone_id in self._zone_subscriptions:
            self._zone_subscriptions[zone_id].discard(websocket)

    async def broadcast(self, message: WebSocketMessage) -> None:
        """Sendet Nachricht an alle verbundenen Clients."""
        if not self._connections:
            return

        data = message.model_dump_json()
        disconnected = set()

        for connection in self._connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.add(connection)

        # Tote Verbindungen aufräumen
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_to_zone(
        self, zone_id: UUID, message: WebSocketMessage
    ) -> None:
        """Sendet Nachricht an alle Clients die eine Zone subscribed haben."""
        subscribers = self._zone_subscriptions.get(zone_id, set())
        if not subscribers:
            return

        data = message.model_dump_json()
        disconnected = set()

        for connection in subscribers:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.add(connection)

        # Tote Verbindungen aufräumen
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(
        self, websocket: WebSocket, message: WebSocketMessage
    ) -> None:
        """Sendet Nachricht an einen spezifischen Client."""
        try:
            await websocket.send_text(message.model_dump_json())
        except Exception:
            self.disconnect(websocket)


# Singleton Instance
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket Endpoint Handler.

    Protokoll:
    - Client sendet: {"type": "subscribe", "zone_id": "..."}
    - Client sendet: {"type": "unsubscribe", "zone_id": "..."}
    - Server sendet: {"type": "reading", "zone_id": "...", "data": {...}}
    - Server sendet: {"type": "alert", "zone_id": "...", "data": {...}}
    """
    await manager.connect(websocket)

    try:
        while True:
            # Auf Client Nachrichten warten
            data = await websocket.receive_text()

            try:
                msg = json.loads(data)
                msg_type = msg.get("type")

                if msg_type == "subscribe" and "zone_id" in msg:
                    zone_id = UUID(msg["zone_id"])
                    manager.subscribe_zone(websocket, zone_id)
                    await manager.send_personal(
                        websocket,
                        WebSocketMessage(
                            type="subscribed",
                            zone_id=str(zone_id),
                            data={"status": "ok"},
                        ),
                    )

                elif msg_type == "unsubscribe" and "zone_id" in msg:
                    zone_id = UUID(msg["zone_id"])
                    manager.unsubscribe_zone(websocket, zone_id)
                    await manager.send_personal(
                        websocket,
                        WebSocketMessage(
                            type="unsubscribed",
                            zone_id=str(zone_id),
                            data={"status": "ok"},
                        ),
                    )

                elif msg_type == "ping":
                    await manager.send_personal(
                        websocket,
                        WebSocketMessage(type="pong", data={}),
                    )

            except json.JSONDecodeError:
                await manager.send_personal(
                    websocket,
                    WebSocketMessage(
                        type="error",
                        data={"message": "Invalid JSON"},
                    ),
                )
            except ValueError as e:
                await manager.send_personal(
                    websocket,
                    WebSocketMessage(
                        type="error",
                        data={"message": str(e)},
                    ),
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# =============================================================================
# Helper Functions für Broadcasting
# =============================================================================


async def broadcast_sensor_reading(
    zone_id: UUID,
    sensor_type: str,
    value: float,
    unit: str,
) -> None:
    """Broadcasted ein neues Sensor Reading an subscribed Clients."""
    await manager.broadcast_to_zone(
        zone_id,
        WebSocketMessage(
            type="reading",
            zone_id=str(zone_id),
            data={
                "sensor_type": sensor_type,
                "value": value,
                "unit": unit,
            },
        ),
    )


async def broadcast_alert(
    zone_id: UUID,
    alert_type: str,
    severity: str,
    message: str,
) -> None:
    """Broadcasted einen Alert an subscribed Clients."""
    await manager.broadcast_to_zone(
        zone_id,
        WebSocketMessage(
            type="alert",
            zone_id=str(zone_id),
            data={
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
            },
        ),
    )


async def broadcast_phase_change(
    zone_id: UUID,
    old_phase: str,
    new_phase: str,
) -> None:
    """Broadcasted eine Phasen-Änderung."""
    await manager.broadcast_to_zone(
        zone_id,
        WebSocketMessage(
            type="phase_change",
            zone_id=str(zone_id),
            data={
                "old_phase": old_phase,
                "new_phase": new_phase,
            },
        ),
    )
