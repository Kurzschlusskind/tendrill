"""
Tendrill Phase Manager

Verwaltung von Wachstumsphasen für Grows und Zonen.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from tendrill.db.repository import Repository
from tendrill.db.session import get_session
from tendrill.knowledge import GrowthPhase, KnowledgeBase
from tendrill.knowledge.defaults import PHASE_SEQUENCE, get_next_phase

if TYPE_CHECKING:
    from tendrill.db.models import Grow, Zone

logger = structlog.get_logger(__name__)


class PhaseManager:
    """
    Manager für Wachstumsphasen.

    Verwaltet Phasenübergänge und berechnet Empfehlungen
    basierend auf der Knowledge Base.
    """

    def __init__(self, knowledge_base: KnowledgeBase | None = None) -> None:
        self.kb = knowledge_base or KnowledgeBase.get_instance()

    # =========================================================================
    # Phase Information
    # =========================================================================

    def get_phase_targets(self, phase: GrowthPhase | str) -> dict:
        """
        Holt alle Zielwerte für eine Phase.

        Returns:
            Dict mit environment und nutrients Targets
        """
        phase_def = self.kb.get_phase(phase)
        return {
            "environment": phase_def.environment.model_dump(),
            "nutrients": phase_def.nutrients.model_dump() if phase_def.nutrients else None,
            "duration_days": phase_def.duration_days,
            "description": phase_def.description,
        }

    def get_expected_duration(self, phase: GrowthPhase | str) -> tuple[int, int]:
        """Gibt die erwartete Dauer einer Phase in Tagen zurück."""
        phase_def = self.kb.get_phase(phase)
        return phase_def.duration_days

    def get_remaining_days(
        self,
        phase: GrowthPhase | str,
        phase_started: datetime,
    ) -> tuple[int, int]:
        """
        Berechnet die verbleibenden Tage in einer Phase.

        Returns:
            Tuple (min_remaining, max_remaining)
        """
        min_days, max_days = self.get_expected_duration(phase)
        days_in_phase = (datetime.utcnow() - phase_started).days

        min_remaining = max(0, min_days - days_in_phase)
        max_remaining = max(0, max_days - days_in_phase)

        return (min_remaining, max_remaining)

    def is_phase_complete(
        self,
        phase: GrowthPhase | str,
        phase_started: datetime,
    ) -> bool:
        """Prüft ob eine Phase die Mindestdauer erreicht hat."""
        min_days, _ = self.get_expected_duration(phase)
        days_in_phase = (datetime.utcnow() - phase_started).days
        return days_in_phase >= min_days

    def should_advance_phase(
        self,
        phase: GrowthPhase | str,
        phase_started: datetime,
    ) -> tuple[bool, str]:
        """
        Prüft ob ein Phasenwechsel empfohlen wird.

        Returns:
            Tuple (should_advance, reason)
        """
        min_days, max_days = self.get_expected_duration(phase)
        days_in_phase = (datetime.utcnow() - phase_started).days

        if days_in_phase < min_days:
            return (False, f"Mindestdauer nicht erreicht ({days_in_phase}/{min_days} Tage)")

        if days_in_phase >= max_days:
            return (True, f"Maximaldauer erreicht ({days_in_phase}/{max_days} Tage)")

        if days_in_phase >= min_days:
            return (True, f"Mindestdauer erreicht ({days_in_phase} Tage), Wechsel möglich")

        return (False, "")

    # =========================================================================
    # Phase Transitions
    # =========================================================================

    async def advance_grow_phase(
        self,
        grow_id: UUID,
        notes: str | None = None,
        force: bool = False,
    ) -> tuple[bool, str, GrowthPhase | None]:
        """
        Wechselt einen Grow zur nächsten Phase.

        Args:
            grow_id: ID des Grows
            notes: Optionale Notizen zum Phasenwechsel
            force: Erzwingt Wechsel auch wenn Mindestdauer nicht erreicht

        Returns:
            Tuple (success, message, new_phase)
        """
        async with get_session() as session:
            repo = Repository(session)
            grow = await repo.get_grow(grow_id)

            if not grow:
                return (False, "Grow nicht gefunden", None)

            if not grow.is_active:
                return (False, "Grow ist nicht aktiv", None)

            current_phase = GrowthPhase(grow.current_phase)
            next_phase = get_next_phase(current_phase)

            if not next_phase:
                return (False, f"Keine weitere Phase nach {current_phase.value}", None)

            # Prüfen ob Wechsel erlaubt
            if not force:
                can_advance, reason = self.should_advance_phase(
                    current_phase, grow.phase_started
                )
                if not can_advance:
                    return (False, reason, None)

            # Phase wechseln
            await repo.update_grow_phase(grow_id, next_phase, notes=notes)

            logger.info(
                "grow_phase_advanced",
                grow_id=str(grow_id),
                old_phase=current_phase.value,
                new_phase=next_phase.value,
            )

            return (True, f"Phase gewechselt zu {next_phase.value}", next_phase)

    async def set_grow_phase(
        self,
        grow_id: UUID,
        phase: GrowthPhase,
        notes: str | None = None,
    ) -> tuple[bool, str]:
        """
        Setzt eine spezifische Phase für einen Grow.

        Args:
            grow_id: ID des Grows
            phase: Neue Phase
            notes: Optionale Notizen

        Returns:
            Tuple (success, message)
        """
        async with get_session() as session:
            repo = Repository(session)
            grow = await repo.get_grow(grow_id)

            if not grow:
                return (False, "Grow nicht gefunden")

            if not grow.is_active:
                return (False, "Grow ist nicht aktiv")

            old_phase = grow.current_phase
            await repo.update_grow_phase(grow_id, phase, notes=notes)

            logger.info(
                "grow_phase_set",
                grow_id=str(grow_id),
                old_phase=old_phase,
                new_phase=phase.value,
            )

            return (True, f"Phase gesetzt: {phase.value}")

    async def sync_zone_phase(self, zone_id: UUID) -> tuple[bool, str]:
        """
        Synchronisiert die Phase einer Zone mit dem aktivsten Grow.

        Args:
            zone_id: ID der Zone

        Returns:
            Tuple (success, message)
        """
        async with get_session() as session:
            repo = Repository(session)
            zone = await repo.get_zone(zone_id)

            if not zone:
                return (False, "Zone nicht gefunden")

            # Aktive Grows in der Zone holen
            grows = await repo.get_active_grows(zone_id=zone_id)

            if not grows:
                return (False, "Keine aktiven Grows in der Zone")

            # Phase des ältesten Grows verwenden (oder Mehrheitsentscheidung)
            oldest_grow = min(grows, key=lambda g: g.grow_started)

            if zone.current_phase != oldest_grow.current_phase:
                await repo.update_zone_phase(zone_id, oldest_grow.current_phase)
                logger.info(
                    "zone_phase_synced",
                    zone_id=str(zone_id),
                    phase=oldest_grow.current_phase,
                )

            return (True, f"Zone-Phase: {oldest_grow.current_phase}")

    # =========================================================================
    # Status & Reporting
    # =========================================================================

    async def get_grow_status(self, grow_id: UUID) -> dict | None:
        """
        Holt den vollständigen Status eines Grows.

        Returns:
            Dict mit Phase-Info, Targets und Empfehlungen
        """
        async with get_session() as session:
            repo = Repository(session)
            grow = await repo.get_grow(grow_id)

            if not grow:
                return None

            current_phase = GrowthPhase(grow.current_phase)
            phase_targets = self.get_phase_targets(current_phase)
            days_in_phase = (datetime.utcnow() - grow.phase_started).days
            total_days = (datetime.utcnow() - grow.grow_started).days
            remaining = self.get_remaining_days(current_phase, grow.phase_started)
            should_advance, advance_reason = self.should_advance_phase(
                current_phase, grow.phase_started
            )

            next_phase = get_next_phase(current_phase)

            return {
                "grow_id": str(grow.id),
                "name": grow.name,
                "strain": grow.strain,
                "current_phase": current_phase.value,
                "phase_started": grow.phase_started.isoformat(),
                "days_in_phase": days_in_phase,
                "total_days": total_days,
                "remaining_days": {
                    "min": remaining[0],
                    "max": remaining[1],
                },
                "targets": phase_targets,
                "next_phase": next_phase.value if next_phase else None,
                "should_advance": should_advance,
                "advance_reason": advance_reason,
            }

    async def get_phase_summary(self) -> list[dict]:
        """
        Holt eine Übersicht aller Phasen mit aktuellen Grows.

        Returns:
            Liste mit Phase-Statistiken
        """
        summary = []

        async with get_session() as session:
            repo = Repository(session)
            grows = await repo.get_active_grows()

            # Grows nach Phase gruppieren
            phase_counts: dict[str, list] = {}
            for grow in grows:
                phase = grow.current_phase
                if phase not in phase_counts:
                    phase_counts[phase] = []
                phase_counts[phase].append(grow)

            # Summary bauen
            for phase in PHASE_SEQUENCE:
                phase_grows = phase_counts.get(phase.value, [])
                duration = self.get_expected_duration(phase)

                summary.append({
                    "phase": phase.value,
                    "active_grows": len(phase_grows),
                    "expected_duration_days": {
                        "min": duration[0],
                        "max": duration[1],
                    },
                    "grow_names": [g.name for g in phase_grows],
                })

        return summary


# =============================================================================
# Singleton Instance
# =============================================================================

_phase_manager: PhaseManager | None = None


def get_phase_manager() -> PhaseManager:
    """Gibt die Singleton Phase Manager Instanz zurück."""
    global _phase_manager
    if _phase_manager is None:
        _phase_manager = PhaseManager()
    return _phase_manager
