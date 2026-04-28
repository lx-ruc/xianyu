"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Ensure .env is loaded before auth module accesses env vars
load_dotenv()

from server.auth import router as auth_router
from server.state import StateBridge


def _try_init_bot(bridge: StateBridge) -> None:
    """Try to initialize XianyuLive bot instance if COOKIES_STR is available."""
    cookies_str = os.getenv("COOKIES_STR", "")
    if not cookies_str or cookies_str == "your_cookies_here":
        logger.warning("COOKIES_STR 未配置，Bot 未初始化（可在 Web 界面启动）")
        return

    try:
        from main import XianyuLive
        from server.state import create_log_sink

        bot = XianyuLive(cookies_str)
        bot.event_bus = bridge.event_bus
        bridge.set_bot(bot)

        # Add log sink for real-time log streaming
        log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
        logger.add(create_log_sink(bridge.event_bus), level=log_level)

        logger.info("Bot 实例已初始化（未启动，可通过 Web 界面控制）")
    except Exception as e:
        logger.error(f"Bot 初始化失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage bot lifecycle within FastAPI."""
    bridge: StateBridge = app.state.bridge  # type: ignore[attr-defined]

    # Auto-init bot if not already done (e.g. started via main.py)
    if bridge.bot is None:
        _try_init_bot(bridge)

    yield

    # Cleanup bot task if we started it
    if bridge.bot_task and not bridge.bot_task.done():
        bridge.bot_task.cancel()
        try:
            await bridge.bot_task
        except asyncio.CancelledError:
            pass


def create_app(bridge: StateBridge | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="闲鱼智能助手",
        description="XianyuAutoAgent Web 管理界面",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Store StateBridge
    app.state.bridge = bridge or StateBridge()

    # CORS for dev mode
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

    # Import and register route modules
    from server.routes import items, config, conversations, analytics, status, ws

    app.include_router(status.router, prefix="/api", tags=["status"])
    app.include_router(items.router, prefix="/api", tags=["items"])
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(analytics.router, prefix="/api", tags=["analytics"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(ws.router, prefix="/ws", tags=["websocket"])

    # Serve frontend static files in production
    dist_dir = Path(__file__).parent.parent / "web" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return app
