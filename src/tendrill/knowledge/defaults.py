"""
Tendrill Knowledge Base - Default Values

Standard-Werte und Konstanten für das System.
"""

from tendrill.knowledge.schemas import GrowthPhase, SensorType

# =============================================================================
# Default Sensor Units
# =============================================================================

SENSOR_UNITS: dict[SensorType, str] = {
    SensorType.TEMPERATURE: "°C",
    SensorType.HUMIDITY: "%",
    SensorType.CO2: "ppm",
    SensorType.LIGHT_PPFD: "µmol/m²/s",
    SensorType.PH: "pH",
    SensorType.EC: "mS/cm",
    SensorType.VPD: "kPa",
    SensorType.WATER_TEMPERATURE: "°C",
    SensorType.WATER_LEVEL: "cm",
}

# =============================================================================
# Phase Sequence
# =============================================================================

PHASE_SEQUENCE: list[GrowthPhase] = [
    GrowthPhase.GERMINATION,
    GrowthPhase.SEEDLING,
    GrowthPhase.VEGETATIVE_EARLY,
    GrowthPhase.VEGETATIVE_LATE,
    GrowthPhase.TRANSITION,
    GrowthPhase.FLOWERING_EARLY,
    GrowthPhase.FLOWERING_MID,
    GrowthPhase.FLOWERING_LATE,
    GrowthPhase.FLUSH,
    GrowthPhase.DRYING,
    GrowthPhase.CURING,
]


def get_next_phase(current: GrowthPhase) -> GrowthPhase | None:
    """Gibt die nächste Phase zurück oder None wenn Ende erreicht."""
    try:
        idx = PHASE_SEQUENCE.index(current)
        if idx < len(PHASE_SEQUENCE) - 1:
            return PHASE_SEQUENCE[idx + 1]
    except ValueError:
        pass
    return None


def get_previous_phase(current: GrowthPhase) -> GrowthPhase | None:
    """Gibt die vorherige Phase zurück oder None wenn am Anfang."""
    try:
        idx = PHASE_SEQUENCE.index(current)
        if idx > 0:
            return PHASE_SEQUENCE[idx - 1]
    except ValueError:
        pass
    return None


# =============================================================================
# VPD Calculation
# =============================================================================


def calculate_vpd(temperature_c: float, humidity_percent: float, leaf_offset_c: float = 2.0) -> float:
    """
    Berechnet den Vapor Pressure Deficit (VPD).

    Args:
        temperature_c: Lufttemperatur in °C
        humidity_percent: Relative Luftfeuchtigkeit in %
        leaf_offset_c: Temperatur-Offset für Blattoberfläche (default: 2°C kühler)

    Returns:
        VPD in kPa
    """
    # Sättigungsdampfdruck der Luft (Tetens-Formel)
    svp_air = 0.6108 * (2.7183 ** ((17.27 * temperature_c) / (temperature_c + 237.3)))

    # Aktueller Dampfdruck
    avp = svp_air * (humidity_percent / 100)

    # Blatttemperatur (typischerweise 1-2°C kühler als Luft)
    leaf_temp = temperature_c - leaf_offset_c

    # Sättigungsdampfdruck am Blatt
    svp_leaf = 0.6108 * (2.7183 ** ((17.27 * leaf_temp) / (leaf_temp + 237.3)))

    # VPD
    vpd = svp_leaf - avp

    return round(vpd, 2)


# =============================================================================
# PPM Conversion
# =============================================================================


def ec_to_ppm_500(ec_ms: float) -> int:
    """Konvertiert EC (mS/cm) zu PPM (500 Scale / US)."""
    return int(ec_ms * 500)


def ec_to_ppm_700(ec_ms: float) -> int:
    """Konvertiert EC (mS/cm) zu PPM (700 Scale / EU)."""
    return int(ec_ms * 700)


def ppm_to_ec_500(ppm: int) -> float:
    """Konvertiert PPM (500 Scale) zu EC (mS/cm)."""
    return round(ppm / 500, 2)


def ppm_to_ec_700(ppm: int) -> float:
    """Konvertiert PPM (700 Scale) zu EC (mS/cm)."""
    return round(ppm / 700, 2)


# =============================================================================
# MQTT Topics
# =============================================================================

MQTT_TOPIC_PREFIX = "tendrill"

# Sensor Topics
MQTT_TOPIC_SENSOR_DATA = f"{MQTT_TOPIC_PREFIX}/sensors/+/data"  # +/data = device_id/data
MQTT_TOPIC_SENSOR_STATUS = f"{MQTT_TOPIC_PREFIX}/sensors/+/status"

# Actuator Topics
MQTT_TOPIC_ACTUATOR_COMMAND = f"{MQTT_TOPIC_PREFIX}/actuators/+/command"
MQTT_TOPIC_ACTUATOR_STATUS = f"{MQTT_TOPIC_PREFIX}/actuators/+/status"

# System Topics
MQTT_TOPIC_ALERTS = f"{MQTT_TOPIC_PREFIX}/alerts"
MQTT_TOPIC_SYSTEM = f"{MQTT_TOPIC_PREFIX}/system"


def get_sensor_topic(device_id: str) -> str:
    """Generiert das MQTT Topic für einen Sensor."""
    return f"{MQTT_TOPIC_PREFIX}/sensors/{device_id}/data"


def get_actuator_topic(device_id: str) -> str:
    """Generiert das MQTT Topic für einen Aktor."""
    return f"{MQTT_TOPIC_PREFIX}/actuators/{device_id}/command"
