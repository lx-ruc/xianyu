"""Status and stats routes."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from server.deps import AccountManagerDep, BotAccountDep, BridgeDep, UserDep

router = APIRouter()


@router.get("/status")
async def get_status(bridge: BridgeDep, _user: UserDep):
    """System status: all bots online/offline, connection state."""
    if not bridge._bots:
        return {"bot_online": False, "accounts": []}

    statuses = bridge.get_bot_statuses()
    accounts = []
    for aid, s in statuses.items():
        bot = bridge.get_bot(aid)
        accounts.append({
            "account_id": aid,
            "display_name": getattr(bot, "display_name", aid),
            "bot_online": s["online"],
            "ws_connected": s["ws_connected"],
            "last_heartbeat": s["last_heartbeat"],
            "manual_mode_count": s["manual_mode_count"],
        })

    return {
        "bot_online": any(s["online"] for s in statuses.values()),
        "accounts": accounts,
    }


@router.get("/accounts")
async def list_accounts(bridge: BridgeDep, _user: UserDep):
    """List all configured accounts with their status."""
    statuses = bridge.get_bot_statuses()
    accounts = []
    for aid, s in statuses.items():
        bot = bridge.get_bot(aid)
        accounts.append({
            "account_id": aid,
            "display_name": getattr(bot, "display_name", aid),
            "online": s["online"],
            "ws_connected": s["ws_connected"],
            "last_heartbeat": s["last_heartbeat"],
            "manual_mode_count": s["manual_mode_count"],
        })
    return accounts


@router.post("/bot/start")
async def start_bot(bot_account: BotAccountDep, account_manager: AccountManagerDep, _user: UserDep):
    """Start a specific bot by account_id."""
    bot, account_id = bot_account

    # If bot exists and is online
    if bot is not None and bot.ws is not None and not bot.ws.closed:
        return {"error": f"账号 [{account_id}] 已在线，无需重复启动"}

    # If bot doesn't exist, try restarting via account manager
    if account_manager:
        success = await account_manager.restart_account(account_id)
        if success:
            return {"message": f"账号 [{account_id}] 启动中..."}
        return {"error": f"账号 [{account_id}] 启动失败，请检查配置"}

    return {"error": "AccountManager 未初始化"}


@router.post("/bot/stop")
async def stop_bot(bot_account: BotAccountDep, account_manager: AccountManagerDep, _user: UserDep):
    """Stop a specific bot by account_id."""
    bot, account_id = bot_account

    if bot is None:
        return {"error": f"账号 [{account_id}] 未初始化"}

    if bot.ws is None:
        return {"error": f"账号 [{account_id}] 已离线"}

    if account_manager:
        success = await account_manager.stop_account(account_id)
        if success:
            return {"message": f"账号 [{account_id}] 正在停止..."}
        return {"error": "停止失败"}

    # fallback: direct stop
    bot.request_stop()
    return {"message": f"账号 [{account_id}] 正在停止..."}


@router.get("/stats/summary")
async def get_stats_summary(bot_account: BotAccountDep, _user: UserDep):
    """Dashboard summary: today's conversations, items, next bump time."""
    from datetime import datetime

    bot, account_id = bot_account

    if bot is None:
        return {
            "account_id": account_id,
            "bot_online": False,
            "today_messages": 0,
            "today_conversations": 0,
            "item_count": 0,
            "manual_mode_count": 0,
        }

    ctx = bot.context_manager

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
        "account_id": account_id,
        "display_name": getattr(bot, "display_name", account_id),
        "bot_online": bot.ws is not None,
        "today_messages": today_msg_count,
        "today_conversations": active_conversations,
        "item_count": item_count,
        "manual_mode_count": len(bot.manual_mode_conversations) if bot else 0,
    }
