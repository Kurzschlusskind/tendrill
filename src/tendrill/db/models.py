"""
Tendrill Database Models

SQLAlchemy Models für PostgreSQL + TimescaleDB.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from tendrill.knowledge.schemas import AlertSeverity, GrowthPhase, SensorType

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """SQLAlchemy Base Class."""

    type_annotation_map = {
        dict: JSONB,
        UUID: PGUUID(as_uuid=True),
    }


# =============================================================================
# Zone Model
# =============================================================================


class Zone(Base):
    """Grow-Zone / Raum."""

    __tablename__ = "zones"
    __table_args__ = (
        Index("idx_zones_active", "is_active", postgresql_where="is_active = TRUE"),
        {"schema": "tendrill"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    zone_type: Mapped[str] = mapped_column(String(50), default="grow_room")
    current_phase: Mapped[str | None] = mapped_column(String(50))
    phase_started: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    devices: Mapped[list["Device"]] = relationship(back_populates="zone")
    grows: Mapped[list["Grow"]] = relationship(back_populates="zone")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="zone")


# =============================================================================
# Device Model
# =============================================================================


class Device(Base):
    """Sensor oder Aktor-Gerät."""

    __tablename__ = "devices"
    __table_args__ = (
        Index("idx_devices_zone", "zone_id"),
        Index("idx_devices_active", "is_active", postgresql_where="is_active = TRUE"),
        {"schema": "tendrill"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    zone_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tendrill.zones.id")
    )
    mqtt_topic: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    zone: Mapped[Zone | None] = relationship(back_populates="devices")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="device")


# =============================================================================
# Grow Model
# =============================================================================


class Grow(Base):
    """Einzelner Grow-Zyklus."""

    __tablename__ = "grows"
    __table_args__ = (
        Index("idx_grows_zone", "zone_id"),
        Index("idx_grows_active", "is_active", postgresql_where="is_active = TRUE"),
        {"schema": "tendrill"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    strain: Mapped[str | None] = mapped_column(String(100))
    zone_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tendrill.zones.id")
    )
    plant_count: Mapped[int] = mapped_column(Integer, default=1)
    current_phase: Mapped[str] = mapped_column(
        String(50), default=GrowthPhase.GERMINATION.value
    )
    phase_started: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    grow_started: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    grow_ended: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    zone: Mapped[Zone | None] = relationship(back_populates="grows")
    phase_history: Mapped[list["PhaseHistory"]] = relationship(back_populates="grow")


# =============================================================================
# Phase History Model
# =============================================================================


class PhaseHistory(Base):
    """Phasen-Verlauf eines Grows."""

    __tablename__ = "phase_history"
    __table_args__ = (
        Index("idx_phase_history_grow", "grow_id", "started_at"),
        {"schema": "tendrill"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    grow_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tendrill.grows.id"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB)

    # Relationships
    grow: Mapped[Grow] = relationship(back_populates="phase_history")


# =============================================================================
# Alert Model
# =============================================================================


class Alert(Base):
    """System-Alert."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index(
            "idx_alerts_zone_unresolved",
            "zone_id",
            "created_at",
            postgresql_where="resolved = FALSE",
        ),
        {"schema": "tendrill"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    zone_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tendrill.zones.id")
    )
    device_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tendrill.devices.id")
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), default=AlertSeverity.WARNING.value
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sensor_type: Mapped[str | None] = mapped_column(String(50))
    value: Mapped[float | None] = mapped_column(Double)
    threshold_min: Mapped[float | None] = mapped_column(Double)
    threshold_max: Mapped[float | None] = mapped_column(Double)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(100))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    zone: Mapped[Zone | None] = relationship(back_populates="alerts")
    device: Mapped[Device | None] = relationship(back_populates="alerts")


# =============================================================================
# Sensor Reading Model (TimescaleDB Hypertable)
# =============================================================================


class SensorReading(Base):
    """
    Sensor-Messwert.

    Diese Tabelle ist eine TimescaleDB Hypertable für optimierte
    Zeitreihen-Speicherung und -Abfragen.

    Note: Primary Key ist (time, device_id) für TimescaleDB Partitionierung.
    """

    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("idx_sensor_readings_device_time", "device_id", "time"),
        Index("idx_sensor_readings_zone_type_time", "zone_id", "sensor_type", "time"),
        {"schema": "tendrill"},
    )

    # TimescaleDB braucht time als Teil des Primary Key
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, nullable=False
    )
    zone_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quality: Mapped[int] = mapped_column(SmallInteger, default=100)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)


# =============================================================================
# Actuator Command Model
# =============================================================================


class ActuatorCommand(Base):
    """Aktor-Befehl."""

    __tablename__ = "actuator_commands"
    __table_args__ = {"schema": "tendrill"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    device_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tendrill.devices.id"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
