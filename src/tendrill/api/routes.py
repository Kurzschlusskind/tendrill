"""
Tendrill API Routes

FastAPI Router mit allen API Endpoints.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from tendrill.db.models import Alert, Device, Grow, Zone
from tendrill.db.repository import Repository
from tendrill.db.session import get_db
from tendrill.knowledge import GrowthPhase, KnowledgeBase
from tendrill.knowledge.schemas import (
    AlertSeverity,
    EnvironmentStatus,
    PhaseDefinition,
    ZoneOverview,
)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class ZoneCreate(BaseModel):
    """Request Model für Zone Erstellung."""

    name: str = Field(..., min_length=1, max_length=100)
    zone_type: str = Field(default="grow_room")
    description: str | None = None
    config: dict | None = None


class ZoneResponse(BaseModel):
    """Response Model für Zone."""

    id: UUID
    name: str
    zone_type: str
    description: str | None
    current_phase: str | None
    phase_started: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceCreate(BaseModel):
    """Request Model für Device Erstellung."""

    name: str = Field(..., min_length=1, max_length=100)
    device_type: str = Field(..., min_length=1, max_length=50)
    mqtt_topic: str = Field(..., min_length=1, max_length=255)
    zone_id: UUID | None = None
    config: dict | None = None


class DeviceResponse(BaseModel):
    """Response Model für Device."""

    id: UUID
    name: str
    device_type: str
    zone_id: UUID | None
    mqtt_topic: str
    is_active: bool
    last_seen: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GrowCreate(BaseModel):
    """Request Model für Grow Erstellung."""

    name: str = Field(..., min_length=1, max_length=100)
    zone_id: UUID
    strain: str | None = None
    plant_count: int = Field(default=1, ge=1)
    config: dict | None = None


class GrowResponse(BaseModel):
    """Response Model für Grow."""

    id: UUID
    name: str
    strain: str | None
    zone_id: UUID | None
    plant_count: int
    current_phase: str
    phase_started: datetime
    grow_started: datetime
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PhaseUpdate(BaseModel):
    """Request Model für Phase Update."""

    phase: GrowthPhase
    notes: str | None = None


class AlertResponse(BaseModel):
    """Response Model für Alert."""

    id: UUID
    zone_id: UUID | None
    device_id: UUID | None
    alert_type: str
    severity: str
    message: str
    sensor_type: str | None
    value: float | None
    acknowledged: bool
    resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ReadingResponse(BaseModel):
    """Response Model für Sensor Reading."""

    time: datetime
    sensor_type: str
    value: float
    unit: str
    quality: int


class ReadingStats(BaseModel):
    """Response Model für aggregierte Reading Statistiken."""

    avg: float | None
    min: float | None
    max: float | None
    count: int


# =============================================================================
# Dependency Injection
# =============================================================================


async def get_repo(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> Repository:
    """Dependency für Repository."""
    return Repository(db)


async def get_knowledge() -> KnowledgeBase:
    """Dependency für Knowledge Base."""
    return KnowledgeBase.get_instance()


# =============================================================================
# Zone Endpoints
# =============================================================================


@router.get("/zones", response_model=list[ZoneResponse], tags=["Zones"])
async def list_zones(
    repo: Annotated[Repository, Depends(get_repo)],
    active_only: bool = True,
) -> list[Zone]:
    """Listet alle Zonen auf."""
    return list(await repo.get_zones(active_only=active_only))


@router.post(
    "/zones",
    response_model=ZoneResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Zones"],
)
async def create_zone(
    data: ZoneCreate,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Zone:
    """Erstellt eine neue Zone."""
    return await repo.create_zone(
        name=data.name,
        zone_type=data.zone_type,
        description=data.description,
        config=data.config,
    )


@router.get("/zones/{zone_id}", response_model=ZoneResponse, tags=["Zones"])
async def get_zone(
    zone_id: UUID,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Zone:
    """Holt eine Zone by ID."""
    zone = await repo.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.get("/zones/{zone_id}/overview", response_model=ZoneOverview, tags=["Zones"])
async def get_zone_overview(
    zone_id: UUID,
    repo: Annotated[Repository, Depends(get_repo)],
) -> ZoneOverview:
    """Holt eine Zonen-Übersicht mit aktuellem Status."""
    zone = await repo.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Aktuelle Readings holen
    readings = await repo.get_latest_readings(zone_id, limit=10)

    # Environment Status bauen
    env = EnvironmentStatus()
    for reading in readings:
        if reading.sensor_type == "temperature":
            env.temperature_c = reading.value
        elif reading.sensor_type == "humidity":
            env.humidity_percent = reading.value
        elif reading.sensor_type == "vpd":
            env.vpd_kpa = reading.value
        elif reading.sensor_type == "co2":
            env.co2_ppm = reading.value
        elif reading.sensor_type == "light_ppfd":
            env.light_ppfd = reading.value
        elif reading.sensor_type == "ph":
            env.ph = reading.value
        elif reading.sensor_type == "ec":
            env.ec_ms = reading.value

    # Alert Count
    alert_count = await repo.get_alert_count(zone_id, unresolved_only=True)

    # Device Count
    devices = await repo.get_devices(zone_id=zone_id)

    return ZoneOverview(
        zone_id=str(zone_id),
        name=zone.name,
        current_phase=GrowthPhase(zone.current_phase) if zone.current_phase else None,
        environment=env,
        alerts_count=alert_count,
        devices_count=len(devices),
    )


@router.put("/zones/{zone_id}/phase", response_model=ZoneResponse, tags=["Zones"])
async def update_zone_phase(
    zone_id: UUID,
    data: PhaseUpdate,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Zone:
    """Aktualisiert die Phase einer Zone."""
    zone = await repo.update_zone_phase(zone_id, data.phase)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


# =============================================================================
# Device Endpoints
# =============================================================================


@router.get("/devices", response_model=list[DeviceResponse], tags=["Devices"])
async def list_devices(
    repo: Annotated[Repository, Depends(get_repo)],
    zone_id: UUID | None = None,
    active_only: bool = True,
) -> list[Device]:
    """Listet alle Devices auf."""
    return list(await repo.get_devices(zone_id=zone_id, active_only=active_only))


@router.post(
    "/devices",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Devices"],
)
async def create_device(
    data: DeviceCreate,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Device:
    """Erstellt ein neues Device."""
    return await repo.create_device(
        name=data.name,
        device_type=data.device_type,
        mqtt_topic=data.mqtt_topic,
        zone_id=data.zone_id,
        config=data.config,
    )


@router.get("/devices/{device_id}", response_model=DeviceResponse, tags=["Devices"])
async def get_device(
    device_id: UUID,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Device:
    """Holt ein Device by ID."""
    device = await repo.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


# =============================================================================
# Grow Endpoints
# =============================================================================


@router.get("/grows", response_model=list[GrowResponse], tags=["Grows"])
async def list_grows(
    repo: Annotated[Repository, Depends(get_repo)],
    zone_id: UUID | None = None,
) -> list[Grow]:
    """Listet aktive Grows auf."""
    return list(await repo.get_active_grows(zone_id=zone_id))


@router.post(
    "/grows",
    response_model=GrowResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Grows"],
)
async def create_grow(
    data: GrowCreate,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Grow:
    """Erstellt einen neuen Grow."""
    return await repo.create_grow(
        name=data.name,
        zone_id=data.zone_id,
        strain=data.strain,
        plant_count=data.plant_count,
        config=data.config,
    )


@router.get("/grows/{grow_id}", response_model=GrowResponse, tags=["Grows"])
async def get_grow(
    grow_id: UUID,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Grow:
    """Holt einen Grow by ID."""
    grow = await repo.get_grow(grow_id)
    if not grow:
        raise HTTPException(status_code=404, detail="Grow not found")
    return grow


@router.put("/grows/{grow_id}/phase", response_model=GrowResponse, tags=["Grows"])
async def update_grow_phase(
    grow_id: UUID,
    data: PhaseUpdate,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Grow:
    """Aktualisiert die Phase eines Grows."""
    grow = await repo.update_grow_phase(grow_id, data.phase, notes=data.notes)
    if not grow:
        raise HTTPException(status_code=404, detail="Grow not found")
    return grow


# =============================================================================
# Readings Endpoints
# =============================================================================


@router.get(
    "/zones/{zone_id}/readings",
    response_model=list[ReadingResponse],
    tags=["Readings"],
)
async def get_zone_readings(
    zone_id: UUID,
    repo: Annotated[Repository, Depends(get_repo)],
    sensor_type: str | None = None,
    hours: int = Query(default=24, ge=1, le=168),
) -> list[dict]:
    """Holt Readings für eine Zone."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    readings = await repo.get_readings_range(
        zone_id=zone_id,
        start_time=start_time,
        end_time=end_time,
        sensor_type=sensor_type,
    )

    return [
        {
            "time": r.time,
            "sensor_type": r.sensor_type,
            "value": r.value,
            "unit": r.unit,
            "quality": r.quality,
        }
        for r in readings
    ]


@router.get(
    "/zones/{zone_id}/readings/stats",
    response_model=ReadingStats,
    tags=["Readings"],
)
async def get_reading_stats(
    zone_id: UUID,
    sensor_type: str,
    repo: Annotated[Repository, Depends(get_repo)],
    hours: int = Query(default=24, ge=1, le=168),
) -> dict:
    """Holt aggregierte Statistiken für einen Sensor."""
    return await repo.get_readings_aggregated(
        zone_id=zone_id,
        sensor_type=sensor_type,
        hours=hours,
    )


# =============================================================================
# Alert Endpoints
# =============================================================================


@router.get("/alerts", response_model=list[AlertResponse], tags=["Alerts"])
async def list_alerts(
    repo: Annotated[Repository, Depends(get_repo)],
    zone_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Alert]:
    """Listet ungelöste Alerts auf."""
    return list(await repo.get_unresolved_alerts(zone_id=zone_id, limit=limit))


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse, tags=["Alerts"])
async def acknowledge_alert(
    alert_id: UUID,
    repo: Annotated[Repository, Depends(get_repo)],
    acknowledged_by: str = "api",
) -> Alert:
    """Bestätigt einen Alert."""
    alert = await repo.acknowledge_alert(alert_id, acknowledged_by)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse, tags=["Alerts"])
async def resolve_alert(
    alert_id: UUID,
    repo: Annotated[Repository, Depends(get_repo)],
) -> Alert:
    """Löst einen Alert."""
    alert = await repo.resolve_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


# =============================================================================
# Knowledge Base Endpoints
# =============================================================================


@router.get("/knowledge/phases", tags=["Knowledge"])
async def list_phases(
    kb: Annotated[KnowledgeBase, Depends(get_knowledge)],
) -> dict[str, PhaseDefinition]:
    """Listet alle Wachstumsphasen auf."""
    return kb.get_all_phases()


@router.get("/knowledge/phases/{phase_name}", tags=["Knowledge"])
async def get_phase_info(
    phase_name: str,
    kb: Annotated[KnowledgeBase, Depends(get_knowledge)],
) -> PhaseDefinition:
    """Holt Informationen zu einer Phase."""
    try:
        return kb.get_phase(phase_name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Phase not found")


@router.get("/knowledge/nutrients/{nutrient_name}", tags=["Knowledge"])
async def get_nutrient_info(
    nutrient_name: str,
    kb: Annotated[KnowledgeBase, Depends(get_knowledge)],
) -> dict:
    """Holt Informationen zu einem Nährstoff."""
    try:
        nutrient = kb.get_nutrient(nutrient_name)
        return nutrient.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Nutrient not found")


@router.get("/knowledge/ph/{medium}", tags=["Knowledge"])
async def get_ph_range(
    medium: str,
    kb: Annotated[KnowledgeBase, Depends(get_knowledge)],
) -> dict:
    """Holt den pH-Bereich für ein Medium."""
    try:
        ph_range = kb.get_ph_range(medium)
        return ph_range.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Medium not found")
