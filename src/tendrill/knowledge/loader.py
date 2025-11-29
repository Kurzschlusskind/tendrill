"""
Tendrill Knowledge Base - YAML Loader

Lädt und cached die Knowledge-Dateien (phases.yaml, nutrients.yaml).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import ValidationError

from tendrill.knowledge.schemas import (
    AlertConfig,
    AutoflowerConfig,
    NutrientsKnowledgeBase,
    PhaseDefinition,
    PhasesKnowledgeBase,
)

if TYPE_CHECKING:
    from tendrill.knowledge.schemas import GrowthPhase


class KnowledgeBaseError(Exception):
    """Fehler beim Laden der Knowledge Base."""

    pass


class KnowledgeBase:
    """
    Knowledge Base Manager.

    Lädt YAML-Dateien und bietet typisierte Zugriffsmethoden.
    """

    _instance: KnowledgeBase | None = None
    _phases: PhasesKnowledgeBase | None = None
    _nutrients: NutrientsKnowledgeBase | None = None

    def __init__(self, data_dir: Path | str | None = None) -> None:
        """
        Initialisiert die Knowledge Base.

        Args:
            data_dir: Pfad zum data/knowledge Verzeichnis.
                     Default: Projektroot/data/knowledge
        """
        if data_dir is None:
            # Default: Relativ zum Paket-Root
            self.data_dir = Path(__file__).parent.parent.parent.parent / "data" / "knowledge"
        else:
            self.data_dir = Path(data_dir)

        if not self.data_dir.exists():
            raise KnowledgeBaseError(f"Knowledge directory not found: {self.data_dir}")

    @classmethod
    def get_instance(cls, data_dir: Path | str | None = None) -> KnowledgeBase:
        """Singleton-Zugriff auf die Knowledge Base."""
        if cls._instance is None:
            cls._instance = cls(data_dir)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset Singleton (für Tests)."""
        cls._instance = None
        cls._phases = None
        cls._nutrients = None

    # =========================================================================
    # YAML Loading
    # =========================================================================

    def _load_yaml(self, filename: str) -> dict:
        """Lädt eine YAML-Datei."""
        filepath = self.data_dir / filename
        if not filepath.exists():
            raise KnowledgeBaseError(f"Knowledge file not found: {filepath}")

        try:
            with open(filepath, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise KnowledgeBaseError(f"YAML parse error in {filename}: {e}") from e

    @functools.cached_property
    def phases(self) -> PhasesKnowledgeBase:
        """Lädt und cached phases.yaml."""
        raw = self._load_yaml("phases.yaml")
        try:
            return PhasesKnowledgeBase.model_validate(raw)
        except ValidationError as e:
            raise KnowledgeBaseError(f"Validation error in phases.yaml: {e}") from e

    @functools.cached_property
    def nutrients(self) -> NutrientsKnowledgeBase:
        """Lädt und cached nutrients.yaml."""
        raw = self._load_yaml("nutrients.yaml")
        try:
            return NutrientsKnowledgeBase.model_validate(raw)
        except ValidationError as e:
            raise KnowledgeBaseError(f"Validation error in nutrients.yaml: {e}") from e

    # =========================================================================
    # Phase Access
    # =========================================================================

    def get_phase(self, phase_name: str | GrowthPhase) -> PhaseDefinition:
        """
        Gibt die Definition einer Wachstumsphase zurück.

        Args:
            phase_name: Name der Phase (z.B. "vegetative_early")

        Returns:
            PhaseDefinition mit environment und nutrients

        Raises:
            KeyError: Phase nicht gefunden
        """
        phase_key = phase_name.value if hasattr(phase_name, "value") else phase_name
        if phase_key not in self.phases.cannabis:
            raise KeyError(f"Unknown phase: {phase_key}")
        return self.phases.cannabis[phase_key]

    def get_all_phases(self) -> dict[str, PhaseDefinition]:
        """Gibt alle Cannabis-Phasen zurück."""
        return self.phases.cannabis

    def get_autoflower_config(self) -> AutoflowerConfig:
        """Gibt die Autoflower-Konfiguration zurück."""
        return self.phases.cannabis_autoflower

    def get_alert_config(self) -> AlertConfig:
        """Gibt die Alert-Grenzwerte zurück."""
        return self.phases.alerts

    # =========================================================================
    # Nutrient Access
    # =========================================================================

    def get_nutrient(self, nutrient_name: str) -> dict:
        """
        Gibt Informationen zu einem Nährstoff zurück.

        Args:
            nutrient_name: z.B. "nitrogen", "calcium", "iron"

        Returns:
            NutrientDeficiency Objekt
        """
        # Suche in allen Kategorien
        for category in [
            self.nutrients.macronutrients,
            self.nutrients.secondary_nutrients,
            self.nutrients.micronutrients,
        ]:
            if nutrient_name in category:
                return category[nutrient_name]
        raise KeyError(f"Unknown nutrient: {nutrient_name}")

    def get_ec_target(self, phase_name: str) -> dict:
        """Gibt EC/PPM Zielwerte für eine Phase zurück."""
        if phase_name not in self.nutrients.ec_ppm_targets:
            raise KeyError(f"No EC targets for phase: {phase_name}")
        return self.nutrients.ec_ppm_targets[phase_name]

    def get_ph_range(self, medium: str) -> dict:
        """Gibt den pH-Bereich für ein Medium zurück."""
        if medium not in self.nutrients.ph_ranges:
            raise KeyError(f"Unknown medium: {medium}")
        return self.nutrients.ph_ranges[medium]

    def get_npk_ratio(self, phase_name: str) -> str:
        """Gibt das NPK-Verhältnis für eine Phase zurück."""
        if phase_name not in self.nutrients.npk_ratios:
            raise KeyError(f"No NPK ratio for phase: {phase_name}")
        return self.nutrients.npk_ratios[phase_name]

    def get_lockout_info(self, nutrient_name: str) -> dict | None:
        """Gibt pH-Lockout-Info für einen Nährstoff zurück."""
        return self.nutrients.nutrient_lockout.get(nutrient_name)

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def is_value_in_range(
        self, value: float, range_tuple: tuple[float, float]
    ) -> bool:
        """Prüft ob ein Wert im Bereich liegt."""
        return range_tuple[0] <= value <= range_tuple[1]

    def check_environment(
        self, phase_name: str, temperature: float | None = None,
        humidity: float | None = None, vpd: float | None = None,
        co2: float | None = None
    ) -> dict[str, dict]:
        """
        Prüft Umgebungswerte gegen Phase-Zielwerte.

        Returns:
            Dict mit Status pro Parameter: {"temperature": {"status": "ok|warning|critical", "value": ..., "target": ...}}
        """
        phase = self.get_phase(phase_name)
        env = phase.environment
        alerts = self.get_alert_config()
        results = {}

        if temperature is not None:
            target = env.temperature_day_c or env.temperature_c
            if target:
                status = "ok"
                if not self.is_value_in_range(temperature, target):
                    if temperature >= alerts.critical.temperature_max_c or temperature <= alerts.critical.temperature_min_c:
                        status = "critical"
                    else:
                        status = "warning"
                results["temperature"] = {
                    "status": status,
                    "value": temperature,
                    "target": target,
                }

        if humidity is not None:
            target = env.humidity_percent
            status = "ok"
            if not self.is_value_in_range(humidity, target):
                if humidity >= alerts.critical.humidity_max_percent or humidity <= alerts.critical.humidity_min_percent:
                    status = "critical"
                else:
                    status = "warning"
            results["humidity"] = {
                "status": status,
                "value": humidity,
                "target": target,
            }

        if vpd is not None and env.vpd_kpa:
            status = "ok"
            if not self.is_value_in_range(vpd, env.vpd_kpa):
                if vpd >= alerts.critical.vpd_max_kpa or vpd <= alerts.critical.vpd_min_kpa:
                    status = "critical"
                else:
                    status = "warning"
            results["vpd"] = {
                "status": status,
                "value": vpd,
                "target": env.vpd_kpa,
            }

        if co2 is not None and env.co2_ppm:
            status = "ok"
            if not self.is_value_in_range(co2, env.co2_ppm):
                status = "warning"
            results["co2"] = {
                "status": status,
                "value": co2,
                "target": env.co2_ppm,
            }

        return results


# Convenience function
def get_knowledge_base(data_dir: Path | str | None = None) -> KnowledgeBase:
    """Gibt die Singleton Knowledge Base Instanz zurück."""
    return KnowledgeBase.get_instance(data_dir)
