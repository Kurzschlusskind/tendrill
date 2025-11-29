"""
Tendrill Sensor Data Ingestion

Verarbeitet eingehende Sensordaten und speichert sie in der Datenbank.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from tendrill.config import get_settings
from tendrill.db.repository import Repository
from tendrill.db.session import get_session
from tendrill.knowledge import KnowledgeBase
from tendrill.sensors.models import SensorPayload
from tendrill.sensors.mqtt import MQTTClient, get_mqtt_client

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class SensorIngestion:
    """
    Sensor Data Ingestion Service.

    Empfängt Sensordaten via MQTT, validiert sie,
    speichert sie in der DB und triggert Alerting.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.mqtt = get_mqtt_client()
        self.knowledge = KnowledgeBase.get_instance(
            self.settings.knowledge_dir
        )
        self._running = False
        self._batch_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._batch_task: asyncio.Task | None = None

        # Device ID -> UUID Mapping Cache
        self._device_cache: dict[str, UUID] = {}
        self._zone_cache: dict[str, UUID] = {}

    async def start(self) -> None:
        """Startet den Ingestion Service."""
        self._running = True

        # Message Handler registrieren
        sensor_topic = f"{self.settings.mqtt.topic_prefix}/sensors/+/data"
        self.mqtt.on_message(sensor_topic, self._handle_sensor_data)

        # Batch Writer starten
        self._batch_task = asyncio.create_task(self._batch_writer())

        logger.info("sensor_ingestion_started")

    async def stop(self) -> None:
        """Stoppt den Ingestion Service."""
        self._running = False
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        logger.info("sensor_ingestion_stopped")

    # =========================================================================
    # Message Handling
    # =========================================================================

    async def _handle_sensor_data(self, topic: str, data: dict) -> None:
        """
        Handler für eingehende Sensor-Daten.

        Wird vom MQTT Client aufgerufen wenn eine Nachricht
        auf dem Sensor Topic empfangen wird.
        """
        try:
            # Payload parsen
            payload = MQTTClient.parse_sensor_payload(data)

            # Device ID aus Topic extrahieren (tendrill/sensors/{device_id}/data)
            topic_device_id = topic.split("/")[2]

            # Validierung: Device ID im Payload sollte zum Topic passen
            if payload.device_id != topic_device_id:
                logger.warning(
                    "sensor_device_mismatch",
                    topic_device=topic_device_id,
                    payload_device=payload.device_id,
                )

            # Verarbeitung
            await self._process_payload(payload)

        except Exception as e:
            logger.error("sensor_ingestion_error", topic=topic, error=str(e))

    async def _process_payload(self, payload: SensorPayload) -> None:
        """Verarbeitet ein validiertes Sensor Payload."""
        timestamp = payload.timestamp or datetime.utcnow()

        # UUIDs auflösen (mit Caching)
        device_uuid = await self._resolve_device_uuid(payload.device_id)
        zone_uuid = await self._resolve_zone_uuid(payload.zone_id)

        if not device_uuid or not zone_uuid:
            logger.warning(
                "sensor_unknown_device_or_zone",
                device_id=payload.device_id,
                zone_id=payload.zone_id,
            )
            return

        # Readings zur Queue hinzufügen
        for reading in payload.readings:
            await self._batch_queue.put({
                "time": timestamp,
                "device_id": device_uuid,
                "zone_id": zone_uuid,
                "sensor_type": reading.type,
                "value": reading.value,
                "unit": reading.unit,
                "quality": reading.quality,
                "extra_data": {},
            })

        # Environment Check für Alerting
        await self._check_environment(payload, zone_uuid)

        # Device Last Seen aktualisieren
        async with get_session() as session:
            repo = Repository(session)
            await repo.update_device_last_seen(device_uuid)

        logger.debug(
            "sensor_data_queued",
            device=payload.device_id,
            readings=len(payload.readings),
        )

    # =========================================================================
    # Batch Writing
    # =========================================================================

    async def _batch_writer(self) -> None:
        """
        Background Task der Readings in Batches schreibt.

        Sammelt Readings für 1 Sekunde oder bis 100 Readings
        und schreibt sie dann als Batch in die DB.
        """
        batch: list[dict] = []
        batch_size = 100
        batch_timeout = 1.0  # Sekunden

        while self._running:
            try:
                # Auf erstes Item warten
                try:
                    item = await asyncio.wait_for(
                        self._batch_queue.get(),
                        timeout=batch_timeout,
                    )
                    batch.append(item)
                except asyncio.TimeoutError:
                    pass

                # Restliche Items aus Queue holen (non-blocking)
                while len(batch) < batch_size:
                    try:
                        item = self._batch_queue.get_nowait()
                        batch.append(item)
                    except asyncio.QueueEmpty:
                        break

                # Batch schreiben wenn nicht leer
                if batch:
                    await self._write_batch(batch)
                    batch = []

            except asyncio.CancelledError:
                # Restliche Items noch schreiben
                if batch:
                    await self._write_batch(batch)
                raise
            except Exception as e:
                logger.error("batch_writer_error", error=str(e))
                batch = []  # Batch verwerfen bei Fehler

    async def _write_batch(self, batch: list[dict]) -> None:
        """Schreibt einen Batch von Readings in die DB."""
        try:
            async with get_session() as session:
                repo = Repository(session)
                count = await repo.insert_readings_batch(batch)
                logger.debug("sensor_batch_written", count=count)
        except Exception as e:
            logger.error("sensor_batch_write_error", error=str(e), count=len(batch))

    # =========================================================================
    # UUID Resolution
    # =========================================================================

    async def _resolve_device_uuid(self, device_id: str) -> UUID | None:
        """
        Löst eine Device ID (String) zu UUID auf.

        Cached Ergebnisse für Performance.
        """
        if device_id in self._device_cache:
            return self._device_cache[device_id]

        async with get_session() as session:
            repo = Repository(session)
            # Device by MQTT Topic suchen
            topic = f"{self.settings.mqtt.topic_prefix}/sensors/{device_id}/data"
            device = await repo.get_device_by_topic(topic)

            if device:
                self._device_cache[device_id] = device.id
                return device.id

        return None

    async def _resolve_zone_uuid(self, zone_id: str) -> UUID | None:
        """
        Löst eine Zone ID (String) zu UUID auf.

        Cached Ergebnisse für Performance.
        """
        if zone_id in self._zone_cache:
            return self._zone_cache[zone_id]

        # Versuche zone_id als UUID zu parsen
        try:
            uuid = UUID(zone_id)
            self._zone_cache[zone_id] = uuid
            return uuid
        except ValueError:
            pass

        # Zone by Name suchen
        async with get_session() as session:
            repo = Repository(session)
            zones = await repo.get_zones(active_only=True)
            for zone in zones:
                if zone.name.lower() == zone_id.lower():
                    self._zone_cache[zone_id] = zone.id
                    return zone.id

        return None

    # =========================================================================
    # Environment Checking
    # =========================================================================

    async def _check_environment(
        self, payload: SensorPayload, zone_uuid: UUID
    ) -> None:
        """
        Prüft Umgebungswerte gegen Phasen-Grenzwerte.

        Erstellt Alerts wenn Werte außerhalb der Toleranz.
        """
        # Zone-Phase holen
        async with get_session() as session:
            repo = Repository(session)
            zone = await repo.get_zone(zone_uuid)

            if not zone or not zone.current_phase:
                return

            # Werte extrahieren
            temp = payload.get_reading("temperature")
            humidity = payload.get_reading("humidity")
            vpd = payload.get_reading("vpd")
            co2 = payload.get_reading("co2")

            # Knowledge Base Check
            try:
                results = self.knowledge.check_environment(
                    zone.current_phase,
                    temperature=temp.value if temp else None,
                    humidity=humidity.value if humidity else None,
                    vpd=vpd.value if vpd else None,
                    co2=co2.value if co2 else None,
                )
            except KeyError:
                # Unbekannte Phase
                return

            # Alerts erstellen für kritische/warning Status
            for param, status in results.items():
                if status["status"] in ("warning", "critical"):
                    await self._create_environment_alert(
                        repo=repo,
                        zone_uuid=zone_uuid,
                        parameter=param,
                        value=status["value"],
                        target=status["target"],
                        severity=status["status"],
                    )

    async def _create_environment_alert(
        self,
        repo: Repository,
        zone_uuid: UUID,
        parameter: str,
        value: float,
        target: tuple[float, float],
        severity: str,
    ) -> None:
        """Erstellt einen Environment Alert."""
        message = (
            f"{parameter.capitalize()} außerhalb Toleranz: "
            f"{value} (Ziel: {target[0]}-{target[1]})"
        )

        await repo.create_alert(
            alert_type="environment",
            message=message,
            severity=severity,
            zone_id=zone_uuid,
            sensor_type=parameter,
            value=value,
            threshold_min=target[0],
            threshold_max=target[1],
        )

        logger.warning(
            "environment_alert_created",
            parameter=parameter,
            value=value,
            target=target,
            severity=severity,
        )


# =============================================================================
# Singleton Instance
# =============================================================================

_ingestion: SensorIngestion | None = None


def get_sensor_ingestion() -> SensorIngestion:
    """Gibt die Singleton Ingestion Instanz zurück."""
    global _ingestion
    if _ingestion is None:
        _ingestion = SensorIngestion()
    return _ingestion
