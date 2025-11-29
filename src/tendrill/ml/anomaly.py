"""
Tendrill Anomaly Detection (Phase 2)

ML-basierte Erkennung von Anomalien in Sensordaten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


@dataclass
class AnomalyResult:
    """Ergebnis einer Anomalie-Prüfung."""

    sensor_type: str
    is_anomaly: bool
    score: float  # 0.0 = normal, 1.0 = definitiv anomal
    value: float
    expected_range: tuple[float, float]
    message: str | None = None


class AnomalyDetector:
    """
    Anomalie-Detektor für Sensordaten.

    Phase 2 Feature - Aktuell Platzhalter-Implementierung
    mit statistischer Baseline-Detection.

    Geplant:
    - Isolation Forest für multivariate Anomalien
    - LSTM für zeitbasierte Muster
    - Online Learning mit Concept Drift Detection
    """

    def __init__(self) -> None:
        # Statistiken pro Sensor für Baseline
        self._stats: dict[str, dict] = {}

        # Konfiguration
        self.min_samples = 100  # Mindestanzahl Samples für Baseline
        self.std_threshold = 3.0  # Standardabweichungen für Anomalie

    def update_baseline(
        self,
        sensor_type: str,
        value: float,
    ) -> None:
        """
        Aktualisiert die Baseline-Statistiken für einen Sensor.

        Verwendet Welford's Online Algorithm für inkrementelles
        Mean/Variance Tracking.
        """
        if sensor_type not in self._stats:
            self._stats[sensor_type] = {
                "count": 0,
                "mean": 0.0,
                "m2": 0.0,  # Für Varianz
                "min": value,
                "max": value,
            }

        stats = self._stats[sensor_type]
        stats["count"] += 1
        n = stats["count"]

        # Welford's Algorithm
        delta = value - stats["mean"]
        stats["mean"] += delta / n
        delta2 = value - stats["mean"]
        stats["m2"] += delta * delta2

        # Min/Max
        stats["min"] = min(stats["min"], value)
        stats["max"] = max(stats["max"], value)

    def get_baseline(self, sensor_type: str) -> dict | None:
        """Holt Baseline-Statistiken für einen Sensor."""
        if sensor_type not in self._stats:
            return None

        stats = self._stats[sensor_type]
        variance = stats["m2"] / stats["count"] if stats["count"] > 1 else 0
        std = variance ** 0.5

        return {
            "count": stats["count"],
            "mean": stats["mean"],
            "std": std,
            "min": stats["min"],
            "max": stats["max"],
        }

    def detect(
        self,
        sensor_type: str,
        value: float,
        update_baseline: bool = True,
    ) -> AnomalyResult:
        """
        Prüft einen Wert auf Anomalien.

        Args:
            sensor_type: Sensortyp
            value: Gemessener Wert
            update_baseline: Baseline mit Wert aktualisieren

        Returns:
            AnomalyResult mit Score und Status
        """
        baseline = self.get_baseline(sensor_type)

        # Nicht genug Daten für Baseline
        if baseline is None or baseline["count"] < self.min_samples:
            if update_baseline:
                self.update_baseline(sensor_type, value)
            return AnomalyResult(
                sensor_type=sensor_type,
                is_anomaly=False,
                score=0.0,
                value=value,
                expected_range=(value, value),
                message="Baseline wird aufgebaut",
            )

        mean = baseline["mean"]
        std = baseline["std"]

        # Bereich für "normal"
        if std > 0:
            lower = mean - (self.std_threshold * std)
            upper = mean + (self.std_threshold * std)
        else:
            # Keine Varianz - exakter Wert erwartet
            lower = mean * 0.9
            upper = mean * 1.1

        # Z-Score berechnen
        if std > 0:
            z_score = abs(value - mean) / std
        else:
            z_score = 0 if value == mean else self.std_threshold + 1

        # Score normalisieren (0-1)
        score = min(1.0, z_score / (self.std_threshold * 2))

        # Anomalie?
        is_anomaly = z_score > self.std_threshold

        # Baseline aktualisieren (nur wenn kein Anomaly)
        if update_baseline and not is_anomaly:
            self.update_baseline(sensor_type, value)

        message = None
        if is_anomaly:
            direction = "hoch" if value > mean else "niedrig"
            message = f"Anomalie: {sensor_type} ist ungewöhnlich {direction} ({z_score:.1f}σ)"
            logger.warning(
                "anomaly_detected",
                sensor_type=sensor_type,
                value=value,
                z_score=z_score,
            )

        return AnomalyResult(
            sensor_type=sensor_type,
            is_anomaly=is_anomaly,
            score=score,
            value=value,
            expected_range=(lower, upper),
            message=message,
        )

    def detect_batch(
        self,
        readings: dict[str, float],
    ) -> list[AnomalyResult]:
        """
        Prüft mehrere Sensoren auf einmal.

        Args:
            readings: Dict mit sensor_type -> value

        Returns:
            Liste von AnomalyResults
        """
        return [
            self.detect(sensor_type, value)
            for sensor_type, value in readings.items()
        ]

    def reset_baseline(self, sensor_type: str | None = None) -> None:
        """Setzt Baseline zurück."""
        if sensor_type:
            self._stats.pop(sensor_type, None)
        else:
            self._stats.clear()

    def get_status(self) -> dict:
        """Holt Status des Detektors."""
        return {
            sensor_type: {
                "baseline_samples": stats["count"],
                "ready": stats["count"] >= self.min_samples,
                **self.get_baseline(sensor_type),
            }
            for sensor_type, stats in self._stats.items()
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_detector: AnomalyDetector | None = None


def get_anomaly_detector() -> AnomalyDetector:
    """Gibt die Singleton Detector Instanz zurück."""
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector
