"""
Tendrill Scheduler

Zeitbasierte Aufgaben und periodische Checks.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Callable, Coroutine, Any

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class ScheduledTask:
    """Einzelne geplante Aufgabe."""

    def __init__(
        self,
        name: str,
        callback: Callable[[], Coroutine[Any, Any, None]],
        interval_seconds: int | None = None,
        run_at: time | None = None,
        enabled: bool = True,
    ) -> None:
        """
        Args:
            name: Name der Aufgabe
            callback: Async Funktion die ausgeführt wird
            interval_seconds: Ausführung alle X Sekunden
            run_at: Tägliche Ausführung zu bestimmter Uhrzeit
            enabled: Aktiviert/Deaktiviert
        """
        self.name = name
        self.callback = callback
        self.interval_seconds = interval_seconds
        self.run_at = run_at
        self.enabled = enabled
        self.last_run: datetime | None = None
        self.run_count = 0
        self.error_count = 0

    async def execute(self) -> bool:
        """Führt die Aufgabe aus."""
        if not self.enabled:
            return False

        try:
            await self.callback()
            self.last_run = datetime.utcnow()
            self.run_count += 1
            logger.debug("task_executed", task=self.name)
            return True
        except Exception as e:
            self.error_count += 1
            logger.error("task_error", task=self.name, error=str(e))
            return False

    def should_run(self) -> bool:
        """Prüft ob die Aufgabe ausgeführt werden sollte."""
        if not self.enabled:
            return False

        now = datetime.utcnow()

        # Interval-basiert
        if self.interval_seconds:
            if self.last_run is None:
                return True
            elapsed = (now - self.last_run).total_seconds()
            return elapsed >= self.interval_seconds

        # Uhrzeit-basiert
        if self.run_at:
            current_time = now.time()
            if self.last_run is None:
                return current_time >= self.run_at
            # Heute noch nicht gelaufen und Uhrzeit erreicht
            if self.last_run.date() < now.date() and current_time >= self.run_at:
                return True

        return False


class Scheduler:
    """
    Task Scheduler für periodische Aufgaben.

    Führt registrierte Tasks basierend auf Intervall oder Uhrzeit aus.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        """Prüft ob der Scheduler läuft."""
        return self._running

    # =========================================================================
    # Task Management
    # =========================================================================

    def add_task(
        self,
        name: str,
        callback: Callable[[], Coroutine[Any, Any, None]],
        interval_seconds: int | None = None,
        run_at: time | None = None,
    ) -> None:
        """
        Registriert eine neue Aufgabe.

        Args:
            name: Eindeutiger Name
            callback: Async Funktion
            interval_seconds: Intervall in Sekunden
            run_at: Uhrzeit für tägliche Ausführung
        """
        if not interval_seconds and not run_at:
            raise ValueError("Either interval_seconds or run_at must be set")

        self._tasks[name] = ScheduledTask(
            name=name,
            callback=callback,
            interval_seconds=interval_seconds,
            run_at=run_at,
        )
        logger.info("task_registered", task=name)

    def remove_task(self, name: str) -> bool:
        """Entfernt eine Aufgabe."""
        if name in self._tasks:
            del self._tasks[name]
            logger.info("task_removed", task=name)
            return True
        return False

    def enable_task(self, name: str) -> bool:
        """Aktiviert eine Aufgabe."""
        if name in self._tasks:
            self._tasks[name].enabled = True
            return True
        return False

    def disable_task(self, name: str) -> bool:
        """Deaktiviert eine Aufgabe."""
        if name in self._tasks:
            self._tasks[name].enabled = False
            return True
        return False

    def get_task_status(self, name: str) -> dict | None:
        """Holt Status einer Aufgabe."""
        task = self._tasks.get(name)
        if not task:
            return None

        return {
            "name": task.name,
            "enabled": task.enabled,
            "interval_seconds": task.interval_seconds,
            "run_at": task.run_at.isoformat() if task.run_at else None,
            "last_run": task.last_run.isoformat() if task.last_run else None,
            "run_count": task.run_count,
            "error_count": task.error_count,
        }

    def get_all_tasks(self) -> list[dict]:
        """Holt Status aller Aufgaben."""
        return [
            self.get_task_status(name)
            for name in self._tasks
        ]

    # =========================================================================
    # Scheduler Loop
    # =========================================================================

    async def start(self) -> None:
        """Startet den Scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("scheduler_started", tasks=len(self._tasks))

    async def stop(self) -> None:
        """Stoppt den Scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("scheduler_stopped")

    async def _run_loop(self) -> None:
        """Hauptschleife des Schedulers."""
        while self._running:
            try:
                # Alle Tasks prüfen
                for task in self._tasks.values():
                    if task.should_run():
                        # Task in eigenem Coroutine ausführen
                        asyncio.create_task(task.execute())

                # Kurz warten vor nächster Prüfung
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_error", error=str(e))
                await asyncio.sleep(5)

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def every(
        self,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
    ) -> Callable:
        """
        Decorator für periodische Tasks.

        Usage:
            @scheduler.every(minutes=5)
            async def my_task():
                ...
        """
        total_seconds = seconds + (minutes * 60) + (hours * 3600)

        def decorator(func: Callable) -> Callable:
            self.add_task(
                name=func.__name__,
                callback=func,
                interval_seconds=total_seconds,
            )
            return func

        return decorator

    def daily(self, at: str) -> Callable:
        """
        Decorator für tägliche Tasks.

        Usage:
            @scheduler.daily(at="08:00")
            async def morning_report():
                ...
        """
        hour, minute = map(int, at.split(":"))
        run_time = time(hour=hour, minute=minute)

        def decorator(func: Callable) -> Callable:
            self.add_task(
                name=func.__name__,
                callback=func,
                run_at=run_time,
            )
            return func

        return decorator


# =============================================================================
# Singleton Instance
# =============================================================================

_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    """Gibt die Singleton Scheduler Instanz zurück."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
