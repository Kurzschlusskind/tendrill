"""
Tendrill Rule Engine

Regelbasierte Auswertung von Sensordaten gegen Zielwerte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

import structlog

from tendrill.knowledge import KnowledgeBase
from tendrill.knowledge.schemas import AlertSeverity

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class RuleOperator(str, Enum):
    """Vergleichsoperatoren für Regeln."""

    LESS_THAN = "lt"
    LESS_EQUAL = "le"
    GREATER_THAN = "gt"
    GREATER_EQUAL = "ge"
    EQUAL = "eq"
    NOT_EQUAL = "ne"
    IN_RANGE = "in_range"
    OUT_OF_RANGE = "out_of_range"


class RuleAction(str, Enum):
    """Aktionen die bei Regel-Match ausgeführt werden."""

    ALERT = "alert"
    LOG = "log"
    ACTUATOR = "actuator"
    WEBHOOK = "webhook"


@dataclass
class RuleResult:
    """Ergebnis einer Regel-Auswertung."""

    rule_name: str
    triggered: bool
    severity: AlertSeverity | None = None
    message: str | None = None
    value: float | None = None
    threshold: float | tuple[float, float] | None = None
    action: RuleAction | None = None
    action_params: dict = field(default_factory=dict)


@dataclass
class Rule:
    """
    Einzelne Regel für die Auswertung.

    Beispiel:
        Rule(
            name="high_temperature",
            sensor_type="temperature",
            operator=RuleOperator.GREATER_THAN,
            threshold=30.0,
            severity=AlertSeverity.WARNING,
            message_template="Temperatur zu hoch: {value}°C (Max: {threshold}°C)",
            action=RuleAction.ALERT,
        )
    """

    name: str
    sensor_type: str
    operator: RuleOperator
    threshold: float | tuple[float, float]
    severity: AlertSeverity = AlertSeverity.WARNING
    message_template: str = "{sensor_type} Wert: {value} (Threshold: {threshold})"
    action: RuleAction = RuleAction.ALERT
    action_params: dict = field(default_factory=dict)
    enabled: bool = True
    cooldown_seconds: int = 60  # Mindestabstand zwischen Alerts

    def evaluate(self, value: float) -> RuleResult:
        """
        Wertet die Regel gegen einen Wert aus.

        Args:
            value: Sensorwert zum Prüfen

        Returns:
            RuleResult mit triggered=True wenn Regel zutrifft
        """
        triggered = False

        match self.operator:
            case RuleOperator.LESS_THAN:
                triggered = value < self.threshold
            case RuleOperator.LESS_EQUAL:
                triggered = value <= self.threshold
            case RuleOperator.GREATER_THAN:
                triggered = value > self.threshold
            case RuleOperator.GREATER_EQUAL:
                triggered = value >= self.threshold
            case RuleOperator.EQUAL:
                triggered = value == self.threshold
            case RuleOperator.NOT_EQUAL:
                triggered = value != self.threshold
            case RuleOperator.IN_RANGE:
                if isinstance(self.threshold, tuple):
                    triggered = self.threshold[0] <= value <= self.threshold[1]
            case RuleOperator.OUT_OF_RANGE:
                if isinstance(self.threshold, tuple):
                    triggered = value < self.threshold[0] or value > self.threshold[1]

        message = None
        if triggered:
            message = self.message_template.format(
                sensor_type=self.sensor_type,
                value=value,
                threshold=self.threshold,
            )

        return RuleResult(
            rule_name=self.name,
            triggered=triggered,
            severity=self.severity if triggered else None,
            message=message,
            value=value,
            threshold=self.threshold,
            action=self.action if triggered else None,
            action_params=self.action_params if triggered else {},
        )


class RuleEngine:
    """
    Regel-Engine für Sensordaten-Auswertung.

    Verwaltet Regeln und wertet sie gegen eingehende Daten aus.
    Unterstützt sowohl statische als auch phasenbasierte Regeln.
    """

    def __init__(self, knowledge_base: KnowledgeBase | None = None) -> None:
        self.kb = knowledge_base or KnowledgeBase.get_instance()
        self._rules: dict[str, Rule] = {}
        self._custom_handlers: dict[str, Callable] = {}

        # Default-Regeln aus Knowledge Base laden
        self._load_default_rules()

    def _load_default_rules(self) -> None:
        """Lädt Standard-Regeln aus der Knowledge Base."""
        alerts = self.kb.get_alert_config()

        # Critical Temperature Rules
        if alerts.critical.temperature_max_c:
            self.add_rule(Rule(
                name="critical_temp_high",
                sensor_type="temperature",
                operator=RuleOperator.GREATER_THAN,
                threshold=alerts.critical.temperature_max_c,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: Temperatur {value}°C überschreitet Maximum von {threshold}°C",
            ))

        if alerts.critical.temperature_min_c:
            self.add_rule(Rule(
                name="critical_temp_low",
                sensor_type="temperature",
                operator=RuleOperator.LESS_THAN,
                threshold=alerts.critical.temperature_min_c,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: Temperatur {value}°C unterschreitet Minimum von {threshold}°C",
            ))

        # Warning Temperature Rules
        if alerts.warning.temperature_high_c:
            self.add_rule(Rule(
                name="warning_temp_high",
                sensor_type="temperature",
                operator=RuleOperator.GREATER_THAN,
                threshold=alerts.warning.temperature_high_c,
                severity=AlertSeverity.WARNING,
                message_template="WARNUNG: Temperatur {value}°C ist hoch (Warnschwelle: {threshold}°C)",
            ))

        if alerts.warning.temperature_low_c:
            self.add_rule(Rule(
                name="warning_temp_low",
                sensor_type="temperature",
                operator=RuleOperator.LESS_THAN,
                threshold=alerts.warning.temperature_low_c,
                severity=AlertSeverity.WARNING,
                message_template="WARNUNG: Temperatur {value}°C ist niedrig (Warnschwelle: {threshold}°C)",
            ))

        # Critical Humidity Rules
        if alerts.critical.humidity_max_percent:
            self.add_rule(Rule(
                name="critical_humidity_high",
                sensor_type="humidity",
                operator=RuleOperator.GREATER_THAN,
                threshold=alerts.critical.humidity_max_percent,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: Luftfeuchtigkeit {value}% überschreitet Maximum von {threshold}%",
            ))

        if alerts.critical.humidity_min_percent:
            self.add_rule(Rule(
                name="critical_humidity_low",
                sensor_type="humidity",
                operator=RuleOperator.LESS_THAN,
                threshold=alerts.critical.humidity_min_percent,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: Luftfeuchtigkeit {value}% unterschreitet Minimum von {threshold}%",
            ))

        # VPD Rules
        if alerts.critical.vpd_max_kpa:
            self.add_rule(Rule(
                name="critical_vpd_high",
                sensor_type="vpd",
                operator=RuleOperator.GREATER_THAN,
                threshold=alerts.critical.vpd_max_kpa,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: VPD {value} kPa überschreitet Maximum von {threshold} kPa",
            ))

        if alerts.critical.vpd_min_kpa:
            self.add_rule(Rule(
                name="critical_vpd_low",
                sensor_type="vpd",
                operator=RuleOperator.LESS_THAN,
                threshold=alerts.critical.vpd_min_kpa,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: VPD {value} kPa unterschreitet Minimum von {threshold} kPa",
            ))

        # pH Rules
        if alerts.critical.ph_max:
            self.add_rule(Rule(
                name="critical_ph_high",
                sensor_type="ph",
                operator=RuleOperator.GREATER_THAN,
                threshold=alerts.critical.ph_max,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: pH {value} überschreitet Maximum von {threshold}",
            ))

        if alerts.critical.ph_min:
            self.add_rule(Rule(
                name="critical_ph_low",
                sensor_type="ph",
                operator=RuleOperator.LESS_THAN,
                threshold=alerts.critical.ph_min,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: pH {value} unterschreitet Minimum von {threshold}",
            ))

        # EC Rule
        if alerts.critical.ec_max_ms:
            self.add_rule(Rule(
                name="critical_ec_high",
                sensor_type="ec",
                operator=RuleOperator.GREATER_THAN,
                threshold=alerts.critical.ec_max_ms,
                severity=AlertSeverity.CRITICAL,
                message_template="KRITISCH: EC {value} mS/cm überschreitet Maximum von {threshold} mS/cm",
            ))

        logger.info("default_rules_loaded", count=len(self._rules))

    # =========================================================================
    # Rule Management
    # =========================================================================

    def add_rule(self, rule: Rule) -> None:
        """Fügt eine Regel hinzu oder aktualisiert sie."""
        self._rules[rule.name] = rule
        logger.debug("rule_added", name=rule.name)

    def remove_rule(self, name: str) -> bool:
        """Entfernt eine Regel."""
        if name in self._rules:
            del self._rules[name]
            logger.debug("rule_removed", name=name)
            return True
        return False

    def get_rule(self, name: str) -> Rule | None:
        """Holt eine Regel by Name."""
        return self._rules.get(name)

    def get_rules(self, sensor_type: str | None = None) -> list[Rule]:
        """Holt alle Regeln, optional gefiltert nach Sensor-Typ."""
        rules = list(self._rules.values())
        if sensor_type:
            rules = [r for r in rules if r.sensor_type == sensor_type]
        return rules

    def enable_rule(self, name: str) -> bool:
        """Aktiviert eine Regel."""
        if name in self._rules:
            self._rules[name].enabled = True
            return True
        return False

    def disable_rule(self, name: str) -> bool:
        """Deaktiviert eine Regel."""
        if name in self._rules:
            self._rules[name].enabled = False
            return True
        return False

    # =========================================================================
    # Evaluation
    # =========================================================================

    def evaluate(
        self,
        sensor_type: str,
        value: float,
    ) -> list[RuleResult]:
        """
        Wertet alle relevanten Regeln für einen Sensorwert aus.

        Args:
            sensor_type: Typ des Sensors (z.B. "temperature")
            value: Gemessener Wert

        Returns:
            Liste von RuleResults für alle getriggerten Regeln
        """
        results = []

        for rule in self._rules.values():
            if not rule.enabled:
                continue
            if rule.sensor_type != sensor_type:
                continue

            result = rule.evaluate(value)
            if result.triggered:
                results.append(result)
                logger.info(
                    "rule_triggered",
                    rule=rule.name,
                    value=value,
                    severity=result.severity.value if result.severity else None,
                )

        return results

    def evaluate_phase(
        self,
        phase_name: str,
        readings: dict[str, float],
    ) -> list[RuleResult]:
        """
        Wertet Sensordaten gegen phasenspezifische Zielwerte aus.

        Args:
            phase_name: Name der aktuellen Phase
            readings: Dict mit sensor_type -> value

        Returns:
            Liste von RuleResults für alle Abweichungen
        """
        results = []

        try:
            phase = self.kb.get_phase(phase_name)
        except KeyError:
            logger.warning("unknown_phase", phase=phase_name)
            return results

        env = phase.environment

        # Temperature Check
        if "temperature" in readings and env.temperature_day_c:
            temp = readings["temperature"]
            target = env.temperature_day_c
            if temp < target[0] or temp > target[1]:
                severity = AlertSeverity.WARNING
                if temp < target[0] - 5 or temp > target[1] + 5:
                    severity = AlertSeverity.CRITICAL

                results.append(RuleResult(
                    rule_name="phase_temperature",
                    triggered=True,
                    severity=severity,
                    message=f"Temperatur {temp}°C außerhalb Phasen-Ziel ({target[0]}-{target[1]}°C)",
                    value=temp,
                    threshold=target,
                    action=RuleAction.ALERT,
                ))

        # Humidity Check
        if "humidity" in readings:
            humidity = readings["humidity"]
            target = env.humidity_percent
            if humidity < target[0] or humidity > target[1]:
                severity = AlertSeverity.WARNING
                if humidity < target[0] - 10 or humidity > target[1] + 10:
                    severity = AlertSeverity.CRITICAL

                results.append(RuleResult(
                    rule_name="phase_humidity",
                    triggered=True,
                    severity=severity,
                    message=f"Luftfeuchtigkeit {humidity}% außerhalb Phasen-Ziel ({target[0]}-{target[1]}%)",
                    value=humidity,
                    threshold=target,
                    action=RuleAction.ALERT,
                ))

        # VPD Check
        if "vpd" in readings and env.vpd_kpa:
            vpd = readings["vpd"]
            target = env.vpd_kpa
            if vpd < target[0] or vpd > target[1]:
                results.append(RuleResult(
                    rule_name="phase_vpd",
                    triggered=True,
                    severity=AlertSeverity.WARNING,
                    message=f"VPD {vpd} kPa außerhalb Phasen-Ziel ({target[0]}-{target[1]} kPa)",
                    value=vpd,
                    threshold=target,
                    action=RuleAction.ALERT,
                ))

        # CO2 Check
        if "co2" in readings and env.co2_ppm:
            co2 = readings["co2"]
            target = env.co2_ppm
            if co2 < target[0] or co2 > target[1]:
                results.append(RuleResult(
                    rule_name="phase_co2",
                    triggered=True,
                    severity=AlertSeverity.INFO,
                    message=f"CO2 {co2} ppm außerhalb Phasen-Ziel ({target[0]}-{target[1]} ppm)",
                    value=co2,
                    threshold=target,
                    action=RuleAction.LOG,
                ))

        return results

    # =========================================================================
    # Custom Handlers
    # =========================================================================

    def register_handler(
        self,
        action: RuleAction,
        handler: Callable[[RuleResult], None],
    ) -> None:
        """Registriert einen Handler für eine Action."""
        self._custom_handlers[action.value] = handler

    async def execute_actions(self, results: list[RuleResult]) -> None:
        """Führt Actions für getriggerte Regeln aus."""
        for result in results:
            if result.action and result.action.value in self._custom_handlers:
                handler = self._custom_handlers[result.action.value]
                try:
                    await handler(result)
                except Exception as e:
                    logger.error(
                        "action_handler_error",
                        action=result.action.value,
                        error=str(e),
                    )


# =============================================================================
# Singleton Instance
# =============================================================================

_rule_engine: RuleEngine | None = None


def get_rule_engine() -> RuleEngine:
    """Gibt die Singleton Rule Engine Instanz zurück."""
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = RuleEngine()
    return _rule_engine
