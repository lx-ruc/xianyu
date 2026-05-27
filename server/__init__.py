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
from server.state import StateBridge, create_log_sink


async def _init_multi_account(bridge: StateBridge) -> None:
    """Initialize AccountManager with multi-account support.

    If accounts.yaml exists and has enabled accounts, use it.
    Otherwise, fall back to single-account mode from COOKIES_STR in .env.
    """
    from account_manager import AccountManager

    manager = AccountManager(bridge, config_path="accounts.yaml")
    enabled = manager.load_config()

    if not enabled:
        # 没有多账号配置，回退到单账号模式
        logger.info("未找到多账号配置，使用单账号兼容模式")
        _fallback_single_bot(bridge, manager)
        return

    # 多账号模式
    logger.info(f"多账号模式: 共 {len(enabled)} 个账号")
    await manager.start_all()


def _fallback_single_bot(bridge: StateBridge, manager) -> None:
    """Fallback: single bot from COOKIES_STR env var."""
    cookies_str = os.getenv("COOKIES_STR", "")
    if not cookies_str or cookies_str == "your_cookies_here":
        logger.warning("COOKIES_STR 未配置，Bot 未初始化（可在 Web 界面启动）")
        return

    try:
        from main import XianyuLive

        bot = XianyuLive(cookies_str)
        bot.event_bus = bridge.event_bus
        bot.xianyu.event_bus = bridge.event_bus
        bridge.set_bot(bot)

        log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
        logger.add(create_log_sink(bridge.event_bus), level=log_level)

        logger.info("Bot 实例已初始化（单账号兼容模式）")
    except Exception as e:
        logger.error(f"Bot 初始化失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage bot lifecycle within FastAPI."""
    bridge: StateBridge = app.state.bridge  # type: ignore[attr-defined]
    manager = getattr(app.state, "account_manager", None)

    # Auto-init if not already done (e.g. started via main.py)
    if not bridge._bots:
        await _init_multi_account(bridge)

    yield

    # Cleanup: stop all bots
    logger.info("应用关闭，停止所有 Bot...")
    if manager:
        await manager.stop_all()
    elif bridge.bot_task and not bridge.bot_task.done():
        bridge.bot_task.cancel()
        try:
            await bridge.bot_task
        except (asyncio.CancelledError, Exception):
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

    # Store AccountManager (created in lifespan)
    from account_manager import AccountManager
    app.state.account_manager = AccountManager(app.state.bridge, config_path="accounts.yaml")

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

    from server.routes import items, config, conversations, analytics, status, ws, orders

    app.include_router(status.router, prefix="/api", tags=["status"])
    app.include_router(items.router, prefix="/api", tags=["items"])
    app.include_router(orders.router, prefix="/api", tags=["orders"])
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(analytics.router, prefix="/api", tags=["analytics"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(ws.router, prefix="/ws", tags=["websocket"])

    # Serve frontend static files in production
    dist_dir = Path(__file__).parent.parent / "web" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return app
