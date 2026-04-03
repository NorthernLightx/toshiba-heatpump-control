import asyncio
import logging
import sys
import webbrowser
from contextlib import asynccontextmanager

import uvicorn

from src.config import settings
from src.manager import manager
from src.routes import app, heartbeat_loop
from src.scheduler import schedule_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    # Startup
    settings.validate()
    logger.info("Connecting to Toshiba cloud...")
    try:
        await manager.connect(settings.toshiba_user, settings.toshiba_pass)
        logger.info("Connected successfully")
    except Exception:
        logger.exception("Failed to connect to Toshiba cloud")
        logger.info("Dashboard will start in disconnected mode")

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    # Start scheduler
    schedule_manager.start()
    logger.info("Scheduler started")

    # Open browser
    url = f"http://{settings.host}:{settings.port}"
    logger.info("Opening %s in your browser...", url)
    webbrowser.open(url)

    yield

    # Shutdown
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass
    schedule_manager.stop()
    await manager.disconnect()
    logger.info("Shutdown complete")


app.router.lifespan_context = lifespan


def main():
    try:
        settings.validate()
    except ValueError:
        settings.prompt_and_save()

    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
