"""Status and stats routes."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from server.deps import BridgeDep, UserDep

router = APIRouter()


@router.get("/status")
async def get_status(bridge: BridgeDep, _user: UserDep):
    """System status: bot online/offline, connection state."""
    bot = bridge.bot
    if bot is None:
        return {"bot_online": False, "ws_connected": False}

    return {
        "bot_online": bot.ws is not None,
        "ws_connected": bot.ws is not None and not bot.ws.closed,
        "last_heartbeat": bot.last_heartbeat_time,
        "last_token_refresh": bot.last_token_refresh_time,
        "manual_mode_count": len(bot.manual_mode_conversations),
    }


@router.post("/bot/start")
async def start_bot(bridge: BridgeDep, _user: UserDep):
    """Start the bot background task."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot 实例未初始化，请通过 main.py 启动"}

    if bot.ws is not None:
        return {"error": "Bot 已在线，无需重复启动"}

    # Reset stop flag and start
    bot._stop_requested = False
    task = asyncio.create_task(bot.main())
    bridge.bot_task = task
    return {"message": "Bot 启动中..."}


@router.post("/bot/stop")
async def stop_bot(bridge: BridgeDep, _user: UserDep):
    """Stop the bot."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot 实例未初始化"}

    if bot.ws is None:
        return {"error": "Bot 已离线"}

    bot.request_stop()
    return {"message": "Bot 正在停止..."}


@router.get("/stats/summary")
async def get_stats_summary(bridge: BridgeDep, _user: UserDep):
    """Dashboard summary: today's conversations, items, next bump time."""
    from datetime import datetime

    bot = bridge.bot
    ctx = bot.context_manager if bot else None

    # Count today's messages from SQLite
    today_msg_count = 0
    active_conversations = 0
    if ctx:
        import sqlite3
        conn = sqlite3.connect(ctx.db_path)
        try:
            cursor = conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM messages WHERE date(timestamp) = ?",
                (today,),
            )
            row = cursor.fetchone()
            active_conversations = row[0] if row else 0

            cursor.execute(
                "SELECT COUNT(*) FROM messages WHERE date(timestamp) = ?",
                (today,),
            )
            row = cursor.fetchone()
            today_msg_count = row[0] if row else 0
        finally:
            conn.close()

    # Item count (try cached data)
    item_count = 0
    try:
        import json
        data_path = "data/my_items_current.json"
        with open(data_path, "r", encoding="utf-8") as f:
            items = json.load(f)
            item_count = len(items)
    except Exception:
        pass

    return {
        "bot_online": bot.ws is not None if bot else False,
        "today_messages": today_msg_count,
        "today_conversations": active_conversations,
        "item_count": item_count,
        "manual_mode_count": len(bot.manual_mode_conversations) if bot else 0,
    }
