"""
Pytest Configuration and Fixtures.
"""

import pytest
from pathlib import Path


@pytest.fixture
def knowledge_dir() -> Path:
    """Pfad zum Knowledge-Verzeichnis."""
    return Path(__file__).parent.parent / "data" / "knowledge"


@pytest.fixture
def sample_sensor_payload() -> dict:
    """Sample MQTT Sensor Payload."""
    return {
        "device_id": "esp32-test-01",
        "zone_id": "zone-main",
        "timestamp": "2024-01-15T14:30:00Z",
        "readings": [
            {"type": "temperature", "value": 24.5, "unit": "°C", "quality": 100},
            {"type": "humidity", "value": 65.2, "unit": "%", "quality": 100},
            {"type": "co2", "value": 850, "unit": "ppm", "quality": 95},
        ],
        "status": "online",
    }


@pytest.fixture
def sample_compact_payload() -> dict:
    """Sample kompaktes ESP32 Payload."""
    return {
        "d": "esp01",
        "z": "main",
        "t": 1705329000,
        "r": [
            ["T", 24.5],
            ["H", 65.2],
            ["C", 850],
        ],
    }
