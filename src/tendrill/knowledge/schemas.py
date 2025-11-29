"""
Tendrill Knowledge Base - Pydantic Schemas

Typisierte Datenmodelle für Wachstumsphasen, Nährstoffe und Alert-Grenzwerte.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class GrowthPhase(str, Enum):
    """Cannabis Wachstumsphasen."""

    GERMINATION = "germination"
    SEEDLING = "seedling"
    VEGETATIVE_EARLY = "vegetative_early"
    VEGETATIVE_LATE = "vegetative_late"
    TRANSITION = "transition"
    FLOWERING_EARLY = "flowering_early"
    FLOWERING_MID = "flowering_mid"
    FLOWERING_LATE = "flowering_late"
    FLUSH = "flush"
    DRYING = "drying"
    CURING = "curing"


class GrowMedium(str, Enum):
    """Anbaumedium."""

    SOIL = "soil"
    COCO = "coco"
    HYDRO = "hydro"
    DWC = "dwc"


class AlertSeverity(str, Enum):
    """Alert-Schweregrad."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SensorType(str, Enum):
    """Sensortypen."""

    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    CO2 = "co2"
    LIGHT_PPFD = "light_ppfd"
    PH = "ph"
    EC = "ec"
    VPD = "vpd"
    WATER_TEMPERATURE = "water_temperature"
    WATER_LEVEL = "water_level"


# =============================================================================
# Type Aliases
# =============================================================================

# Range als [min, max] Tuple
Range = Annotated[tuple[float, float], Field(min_length=2, max_length=2)]


# =============================================================================
# Environment Schemas
# =============================================================================


class EnvironmentParams(BaseModel):
    """Umgebungsparameter für eine Wachstumsphase."""

    temperature_day_c: Range | None = None
    temperature_night_c: Range | None = None
    temperature_c: Range | None = None  # Für Drying/Curing
    humidity_percent: Range
    vpd_kpa: Range | None = None
    light_schedule: str | None = None  # Format: "18/6" oder "dark"
    light_ppfd: Range | int | None = None
    light: str | None = None  # "dark" für Drying/Curing
    co2_ppm: Range | None = None
    airflow: str | None = None

    model_config = {"extra": "allow"}


class NutrientParams(BaseModel):
    """Nährstoffparameter für eine Wachstumsphase."""

    ec_ms: Range | float
    ppm: Range | float
    ph: Range | None = None
    npk_ratio: str | None = None
    nitrogen_mg_l: Range | None = None
    phosphorus_mg_l: Range | None = None
    potassium_mg_l: Range | None = None
    notes: str | None = None

    model_config = {"extra": "allow"}


class PhaseDefinition(BaseModel):
    """Definition einer einzelnen Wachstumsphase."""

    duration_days: Range
    description: str
    environment: EnvironmentParams
    nutrients: NutrientParams | None = None


# =============================================================================
# Nutrient Schemas
# =============================================================================


class NutrientDeficiency(BaseModel):
    """Nährstoff mit Mangel/Überschuss-Symptomen."""

    symbol: str
    function: str
    deficiency_symptoms: list[str]
    toxicity_symptoms: list[str] | None = None
    optimal_mg_l: dict[str, Range] | Range | None = None
    notes: str | None = None


class NutrientLockout(BaseModel):
    """pH-Bereiche für Nährstoff-Lockout."""

    lockout_below_ph: float | None = None
    lockout_above_ph: float | None = None


class ECPPMTarget(BaseModel):
    """EC/PPM Zielwerte für eine Phase."""

    ec_ms: Range
    ppm_500: Range
    ppm_700: Range | None = None


class PHRange(BaseModel):
    """pH-Bereiche für ein Medium."""

    optimal: Range
    acceptable: Range | None = None


# =============================================================================
# Alert Schemas
# =============================================================================


class AlertThresholds(BaseModel):
    """Alert-Grenzwerte."""

    # Critical
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None
    humidity_max_percent: float | None = None
    humidity_min_percent: float | None = None
    vpd_max_kpa: float | None = None
    vpd_min_kpa: float | None = None
    ph_max: float | None = None
    ph_min: float | None = None
    ec_max_ms: float | None = None

    # Warning
    temperature_high_c: float | None = None
    temperature_low_c: float | None = None
    humidity_high_percent: float | None = None
    humidity_low_percent: float | None = None

    model_config = {"extra": "allow"}


class AlertConfig(BaseModel):
    """Alert-Konfiguration mit critical und warning Grenzwerten."""

    critical: AlertThresholds
    warning: AlertThresholds


# =============================================================================
# Autoflower Config
# =============================================================================


class AutoflowerConfig(BaseModel):
    """Autoflower-spezifische Konfiguration."""

    light_schedule: str
    total_duration_days: Range
    vegetative_days: Range
    flowering_days: Range


# =============================================================================
# Top-Level Knowledge Base Schemas
# =============================================================================


class PhasesKnowledgeBase(BaseModel):
    """Komplette Wachstumsphasen-Wissensbasis (phases.yaml)."""

    cannabis: dict[str, PhaseDefinition]
    cannabis_autoflower: AutoflowerConfig
    alerts: AlertConfig


class NutrientsKnowledgeBase(BaseModel):
    """Komplette Nährstoff-Wissensbasis (nutrients.yaml)."""

    macronutrients: dict[str, NutrientDeficiency]
    secondary_nutrients: dict[str, NutrientDeficiency]
    micronutrients: dict[str, NutrientDeficiency]
    ec_ppm_targets: dict[str, ECPPMTarget]
    ph_ranges: dict[str, PHRange]
    npk_ratios: dict[str, str]
    nutrient_lockout: dict[str, NutrientLockout]


# =============================================================================
# Sensor Reading Schema
# =============================================================================


class SensorReading(BaseModel):
    """Einzelne Sensor-Messung."""

    device_id: str
    zone_id: str
    sensor_type: SensorType
    value: float
    unit: str
    quality: int = Field(default=100, ge=0, le=100)
    metadata: dict | None = None

    model_config = {"extra": "allow"}


class SensorReadingBatch(BaseModel):
    """Batch von Sensor-Messungen (MQTT Payload)."""

    device_id: str
    zone_id: str
    timestamp: str | None = None
    readings: list[SensorReading]


# =============================================================================
# API Response Schemas
# =============================================================================


class PhaseStatus(BaseModel):
    """Aktueller Phasen-Status einer Zone/Pflanze."""

    phase: GrowthPhase
    day_in_phase: int
    total_days: int
    expected_duration: Range
    environment_targets: EnvironmentParams
    nutrient_targets: NutrientParams | None


class EnvironmentStatus(BaseModel):
    """Aktueller Umgebungs-Status."""

    temperature_c: float | None = None
    humidity_percent: float | None = None
    vpd_kpa: float | None = None
    co2_ppm: float | None = None
    light_ppfd: float | None = None
    ph: float | None = None
    ec_ms: float | None = None


class ZoneOverview(BaseModel):
    """Übersicht einer Grow-Zone."""

    zone_id: str
    name: str
    current_phase: GrowthPhase | None
    environment: EnvironmentStatus
    alerts_count: int = 0
    devices_count: int = 0
