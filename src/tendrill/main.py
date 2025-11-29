"""
Tendrill - Main Application Entry Point

FastAPI Application mit MQTT Integration.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tendrill.api.routes import router
from tendrill.api.websocket import websocket_endpoint
from tendrill.config import get_settings
from tendrill.db.session import close_db, init_db
from tendrill.sensors.ingestion import get_sensor_ingestion
from tendrill.sensors.mqtt import get_mqtt_client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# Structlog konfigurieren
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer() if get_settings().is_development else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application Lifespan Manager.

    Startet und stoppt alle Services beim App Start/Stop.
    """
    settings = get_settings()

    logger.info(
        "tendrill_starting",
        env=settings.env,
        debug=settings.debug,
    )

    # Database initialisieren (optional im Development Mode)
    try:
        await init_db()
        logger.info("database_connected")
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        if not settings.is_development:
            raise
        logger.warning("running_without_database", hint="Start PostgreSQL or use docker-compose")

    # MQTT Client und Sensor Ingestion starten (optional)
    mqtt_client = get_mqtt_client()
    ingestion = get_sensor_ingestion()
    mqtt_task = None

    try:
        mqtt_task = asyncio.create_task(mqtt_client.start())
        await ingestion.start()
    except Exception as e:
        logger.warning("mqtt_connection_failed", error=str(e), hint="MQTT broker not available")

    logger.info("tendrill_started")

    try:
        yield
    finally:
        # Cleanup
        logger.info("tendrill_stopping")

        try:
            await ingestion.stop()
            await mqtt_client.stop()
            if mqtt_task:
                mqtt_task.cancel()
                try:
                    await mqtt_task
                except asyncio.CancelledError:
                    pass
        except Exception:
            pass

        try:
            await close_db()
        except Exception:
            pass

        logger.info("tendrill_stopped")


def create_app() -> FastAPI:
    """
    Application Factory.

    Erstellt und konfiguriert die FastAPI Application.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Hybrid-Supervisor für automatisiertes Grow-Monitoring",
        version=settings.version,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Router
    app.include_router(router, prefix=settings.api_prefix)

    # WebSocket Route
    app.websocket("/ws")(websocket_endpoint)

    # Health Check
    @app.get("/health", tags=["System"])
    async def health_check() -> dict:
        """Health Check Endpoint."""
        return {
            "status": "healthy",
            "version": settings.version,
            "env": settings.env,
        }

    return app


# Application Instance
app = create_app()


def main() -> None:
    """CLI Entry Point."""
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "tendrill.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_level=settings.logging.level.lower(),
    )


if __name__ == "__main__":
    main()
