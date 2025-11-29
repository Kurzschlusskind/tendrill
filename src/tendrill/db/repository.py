"""
Tendrill Database Repository

Data Access Layer mit typisierten Methoden.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tendrill.db.models import (
    Alert,
    Device,
    Grow,
    PhaseHistory,
    SensorReading,
    Zone,
)
from tendrill.knowledge.schemas import AlertSeverity, GrowthPhase

if TYPE_CHECKING:
    from collections.abc import Sequence


class Repository:
    """
    Zentrales Repository für Datenbankoperationen.

    Alle Methoden sind async und erwarten eine Session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # Zone Operations
    # =========================================================================

    async def get_zone(self, zone_id: UUID) -> Zone | None:
        """Holt eine Zone by ID."""
        return await self.session.get(Zone, zone_id)

    async def get_zones(self, active_only: bool = True) -> Sequence[Zone]:
        """Holt alle Zonen."""
        query = select(Zone)
        if active_only:
            query = query.where(Zone.is_active == True)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def create_zone(
        self,
        name: str,
        zone_type: str = "grow_room",
        description: str | None = None,
        config: dict | None = None,
    ) -> Zone:
        """Erstellt eine neue Zone."""
        zone = Zone(
            name=name,
            zone_type=zone_type,
            description=description,
            config=config or {},
        )
        self.session.add(zone)
        await self.session.flush()
        return zone

    async def update_zone_phase(
        self, zone_id: UUID, phase: GrowthPhase | str
    ) -> Zone | None:
        """Aktualisiert die aktuelle Phase einer Zone."""
        phase_value = phase.value if isinstance(phase, GrowthPhase) else phase
        stmt = (
            update(Zone)
            .where(Zone.id == zone_id)
            .values(current_phase=phase_value, phase_started=datetime.utcnow())
            .returning(Zone)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # =========================================================================
    # Device Operations
    # =========================================================================

    async def get_device(self, device_id: UUID) -> Device | None:
        """Holt ein Device by ID."""
        return await self.session.get(Device, device_id)

    async def get_device_by_topic(self, mqtt_topic: str) -> Device | None:
        """Holt ein Device by MQTT Topic."""
        query = select(Device).where(Device.mqtt_topic == mqtt_topic)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_devices(
        self, zone_id: UUID | None = None, active_only: bool = True
    ) -> Sequence[Device]:
        """Holt Devices, optional gefiltert nach Zone."""
        query = select(Device)
        if zone_id:
            query = query.where(Device.zone_id == zone_id)
        if active_only:
            query = query.where(Device.is_active == True)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def create_device(
        self,
        name: str,
        device_type: str,
        mqtt_topic: str,
        zone_id: UUID | None = None,
        config: dict | None = None,
    ) -> Device:
        """Erstellt ein neues Device."""
        device = Device(
            name=name,
            device_type=device_type,
            mqtt_topic=mqtt_topic,
            zone_id=zone_id,
            config=config or {},
        )
        self.session.add(device)
        await self.session.flush()
        return device

    async def update_device_last_seen(self, device_id: UUID) -> None:
        """Aktualisiert last_seen Timestamp eines Devices."""
        stmt = (
            update(Device)
            .where(Device.id == device_id)
            .values(last_seen=datetime.utcnow())
        )
        await self.session.execute(stmt)

    # =========================================================================
    # Grow Operations
    # =========================================================================

    async def get_grow(self, grow_id: UUID) -> Grow | None:
        """Holt einen Grow by ID."""
        return await self.session.get(Grow, grow_id)

    async def get_active_grows(self, zone_id: UUID | None = None) -> Sequence[Grow]:
        """Holt aktive Grows."""
        query = select(Grow).where(Grow.is_active == True)
        if zone_id:
            query = query.where(Grow.zone_id == zone_id)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def create_grow(
        self,
        name: str,
        zone_id: UUID,
        strain: str | None = None,
        plant_count: int = 1,
        config: dict | None = None,
    ) -> Grow:
        """Erstellt einen neuen Grow."""
        grow = Grow(
            name=name,
            zone_id=zone_id,
            strain=strain,
            plant_count=plant_count,
            config=config or {},
        )
        self.session.add(grow)
        await self.session.flush()

        # Erste Phase History erstellen
        await self.create_phase_history(grow.id, GrowthPhase.GERMINATION)

        return grow

    async def update_grow_phase(
        self, grow_id: UUID, phase: GrowthPhase | str, notes: str | None = None
    ) -> Grow | None:
        """Aktualisiert die Phase eines Grows."""
        grow = await self.get_grow(grow_id)
        if not grow:
            return None

        # Alte Phase beenden
        await self.end_current_phase(grow_id)

        # Neue Phase setzen
        phase_value = phase.value if isinstance(phase, GrowthPhase) else phase
        grow.current_phase = phase_value
        grow.phase_started = datetime.utcnow()

        # Neue Phase History erstellen
        await self.create_phase_history(grow_id, phase, notes=notes)

        await self.session.flush()
        return grow

    # =========================================================================
    # Phase History Operations
    # =========================================================================

    async def create_phase_history(
        self,
        grow_id: UUID,
        phase: GrowthPhase | str,
        notes: str | None = None,
        config_snapshot: dict | None = None,
    ) -> PhaseHistory:
        """Erstellt einen Phase History Eintrag."""
        phase_value = phase.value if isinstance(phase, GrowthPhase) else phase
        history = PhaseHistory(
            grow_id=grow_id,
            phase=phase_value,
            started_at=datetime.utcnow(),
            notes=notes,
            config_snapshot=config_snapshot,
        )
        self.session.add(history)
        await self.session.flush()
        return history

    async def end_current_phase(self, grow_id: UUID) -> None:
        """Beendet die aktuelle Phase eines Grows."""
        stmt = (
            update(PhaseHistory)
            .where(PhaseHistory.grow_id == grow_id, PhaseHistory.ended_at == None)
            .values(ended_at=datetime.utcnow())
        )
        await self.session.execute(stmt)

    async def get_phase_history(self, grow_id: UUID) -> Sequence[PhaseHistory]:
        """Holt die Phase History eines Grows."""
        query = (
            select(PhaseHistory)
            .where(PhaseHistory.grow_id == grow_id)
            .order_by(PhaseHistory.started_at)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    # =========================================================================
    # Sensor Reading Operations
    # =========================================================================

    async def insert_reading(
        self,
        device_id: UUID,
        zone_id: UUID,
        sensor_type: str,
        value: float,
        unit: str,
        quality: int = 100,
        extra_data: dict | None = None,
        timestamp: datetime | None = None,
    ) -> SensorReading:
        """Fügt einen Sensor-Messwert ein."""
        reading = SensorReading(
            time=timestamp or datetime.utcnow(),
            device_id=device_id,
            zone_id=zone_id,
            sensor_type=sensor_type,
            value=value,
            unit=unit,
            quality=quality,
            extra_data=extra_data or {},
        )
        self.session.add(reading)
        await self.session.flush()
        return reading

    async def insert_readings_batch(
        self, readings: list[dict]
    ) -> int:
        """
        Bulk Insert von Sensor-Messwerten.

        Returns:
            Anzahl eingefügter Readings
        """
        objects = [SensorReading(**r) for r in readings]
        self.session.add_all(objects)
        await self.session.flush()
        return len(objects)

    async def get_latest_readings(
        self,
        zone_id: UUID,
        sensor_types: list[str] | None = None,
        limit: int = 1,
    ) -> Sequence[SensorReading]:
        """Holt die neuesten Readings für eine Zone."""
        query = (
            select(SensorReading)
            .where(SensorReading.zone_id == zone_id)
            .order_by(SensorReading.time.desc())
            .limit(limit)
        )
        if sensor_types:
            query = query.where(SensorReading.sensor_type.in_(sensor_types))
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_readings_range(
        self,
        zone_id: UUID,
        start_time: datetime,
        end_time: datetime,
        sensor_type: str | None = None,
    ) -> Sequence[SensorReading]:
        """Holt Readings in einem Zeitbereich."""
        query = (
            select(SensorReading)
            .where(
                SensorReading.zone_id == zone_id,
                SensorReading.time >= start_time,
                SensorReading.time <= end_time,
            )
            .order_by(SensorReading.time)
        )
        if sensor_type:
            query = query.where(SensorReading.sensor_type == sensor_type)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_readings_aggregated(
        self,
        zone_id: UUID,
        sensor_type: str,
        hours: int = 24,
    ) -> dict:
        """
        Holt aggregierte Statistiken für einen Sensor.

        Returns:
            Dict mit avg, min, max, count
        """
        start_time = datetime.utcnow() - timedelta(hours=hours)
        query = select(
            func.avg(SensorReading.value).label("avg"),
            func.min(SensorReading.value).label("min"),
            func.max(SensorReading.value).label("max"),
            func.count(SensorReading.value).label("count"),
        ).where(
            SensorReading.zone_id == zone_id,
            SensorReading.sensor_type == sensor_type,
            SensorReading.time >= start_time,
        )
        result = await self.session.execute(query)
        row = result.one()
        return {
            "avg": float(row.avg) if row.avg else None,
            "min": float(row.min) if row.min else None,
            "max": float(row.max) if row.max else None,
            "count": row.count,
        }

    # =========================================================================
    # Alert Operations
    # =========================================================================

    async def create_alert(
        self,
        alert_type: str,
        message: str,
        severity: AlertSeverity | str = AlertSeverity.WARNING,
        zone_id: UUID | None = None,
        device_id: UUID | None = None,
        sensor_type: str | None = None,
        value: float | None = None,
        threshold_min: float | None = None,
        threshold_max: float | None = None,
    ) -> Alert:
        """Erstellt einen neuen Alert."""
        severity_value = (
            severity.value if isinstance(severity, AlertSeverity) else severity
        )
        alert = Alert(
            alert_type=alert_type,
            message=message,
            severity=severity_value,
            zone_id=zone_id,
            device_id=device_id,
            sensor_type=sensor_type,
            value=value,
            threshold_min=threshold_min,
            threshold_max=threshold_max,
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_unresolved_alerts(
        self, zone_id: UUID | None = None, limit: int = 100
    ) -> Sequence[Alert]:
        """Holt ungelöste Alerts."""
        query = (
            select(Alert)
            .where(Alert.resolved == False)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        if zone_id:
            query = query.where(Alert.zone_id == zone_id)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def acknowledge_alert(
        self, alert_id: UUID, acknowledged_by: str
    ) -> Alert | None:
        """Bestätigt einen Alert."""
        stmt = (
            update(Alert)
            .where(Alert.id == alert_id)
            .values(
                acknowledged=True,
                acknowledged_at=datetime.utcnow(),
                acknowledged_by=acknowledged_by,
            )
            .returning(Alert)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def resolve_alert(self, alert_id: UUID) -> Alert | None:
        """Löst einen Alert."""
        stmt = (
            update(Alert)
            .where(Alert.id == alert_id)
            .values(resolved=True, resolved_at=datetime.utcnow())
            .returning(Alert)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_alert_count(
        self, zone_id: UUID | None = None, unresolved_only: bool = True
    ) -> int:
        """Zählt Alerts."""
        query = select(func.count(Alert.id))
        if zone_id:
            query = query.where(Alert.zone_id == zone_id)
        if unresolved_only:
            query = query.where(Alert.resolved == False)
        result = await self.session.execute(query)
        return result.scalar() or 0
