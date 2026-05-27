"""Conversation management routes."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from server.deps import BotAccountDep, BridgeDep, UserDep

router = APIRouter()


def _resolve_bot(bridge: BridgeDep, bot_account: BotAccountDep):
    """Resolve bot instance from account-aware dep, with fallback to active bot."""
    bot, account_id = bot_account
    if bot is None:
        # fallback to bridge.bot (backward compat)
        bot = bridge.bot
    return bot


@router.get("/conversations")
async def list_conversations(
    bridge: BridgeDep,
    bot_account: BotAccountDep,
    _user: UserDep,
    item_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List recent conversations with latest message preview."""
    bot = _resolve_bot(bridge, bot_account)
    if bot is None:
        return {"conversations": [], "total": 0}

    ctx = bot.context_manager
    conn = sqlite3.connect(ctx.db_path)
    try:
        cursor = conn.cursor()

        if item_id:
            cursor.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM messages WHERE chat_id IS NOT NULL AND item_id = ?",
                (item_id,),
            )
        else:
            cursor.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM messages WHERE chat_id IS NOT NULL",
            )
        total = cursor.fetchone()[0]

        if item_id:
            cursor.execute(
                """
                SELECT m.chat_id, m.user_id, m.item_id, m.content, m.timestamp, m.role
                FROM messages m
                INNER JOIN (
                    SELECT chat_id, MAX(timestamp) as max_ts
                    FROM messages WHERE chat_id IS NOT NULL AND item_id = ?
                    GROUP BY chat_id
                ) latest ON m.chat_id = latest.chat_id AND m.timestamp = latest.max_ts
                ORDER BY m.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (item_id, page_size, (page - 1) * page_size),
            )
        else:
            cursor.execute(
                """
                SELECT m.chat_id, m.user_id, m.item_id, m.content, m.timestamp, m.role
                FROM messages m
                INNER JOIN (
                    SELECT chat_id, MAX(timestamp) as max_ts
                    FROM messages WHERE chat_id IS NOT NULL
                    GROUP BY chat_id
                ) latest ON m.chat_id = latest.chat_id AND m.timestamp = latest.max_ts
                ORDER BY m.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, (page - 1) * page_size),
            )

        rows = cursor.fetchall()
        conversations = []
        for row in rows:
            chat_id, user_id, item_id_val, content, timestamp, role = row
            mode = "manual" if bot.is_manual_mode(chat_id) else "auto"
            bargain_count = ctx.get_bargain_count_by_chat(chat_id)

            conversations.append({
                "chat_id": chat_id,
                "user_id": user_id,
                "item_id": item_id_val,
                "last_message": content[:100] if content else "",
                "last_role": role,
                "last_time": timestamp,
                "mode": mode,
                "bargain_count": bargain_count,
            })

        return {"conversations": conversations, "total": total, "page": page, "page_size": page_size}
    finally:
        conn.close()


@router.get("/conversations/{chat_id}")
async def get_conversation(chat_id: str, bridge: BridgeDep, bot_account: BotAccountDep, _user: UserDep):
    """Get conversation detail with full message history."""
    bot = _resolve_bot(bridge, bot_account)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not initialized")

    ctx = bot.context_manager
    conn = sqlite3.connect(ctx.db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, role, content, timestamp, user_id, item_id FROM messages WHERE chat_id = ? ORDER BY timestamp ASC",
            (chat_id,),
        )
        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="会话不存在")

        messages = [
            {"id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]}
            for r in rows
        ]

        mode = "manual" if bot.is_manual_mode(chat_id) else "auto"
        bargain_count = ctx.get_bargain_count_by_chat(chat_id)

        return {
            "chat_id": chat_id,
            "mode": mode,
            "bargain_count": bargain_count,
            "item_id": rows[0][5],
            "messages": messages,
        }
    finally:
        conn.close()


class ReplyBody(BaseModel):
    content: str


@router.post("/conversations/{chat_id}/reply")
async def manual_reply(chat_id: str, body: ReplyBody, bridge: BridgeDep, bot_account: BotAccountDep, _user: UserDep):
    """Send a manual reply in a conversation."""
    bot = _resolve_bot(bridge, bot_account)
    if bot is None or bot.ws is None:
        raise HTTPException(status_code=503, detail="机器人未连接，无法发送消息")

    ctx = bot.context_manager
    conn = sqlite3.connect(ctx.db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM messages WHERE chat_id = ? AND role = 'user' LIMIT 1",
            (chat_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="会话不存在")
        to_id = row[0]
    finally:
        conn.close()

    await bot.send_msg(bot.ws, chat_id, to_id, body.content)
    ctx.add_message_by_chat(chat_id, bot.myid, "", "assistant", body.content)

    return {"success": True, "message": "消息已发送"}


class ToggleModeBody(BaseModel):
    mode: str


@router.post("/conversations/{chat_id}/toggle-mode")
async def toggle_mode(chat_id: str, body: ToggleModeBody, bridge: BridgeDep, bot_account: BotAccountDep, _user: UserDep):
    """Toggle conversation between auto and manual mode."""
    bot = _resolve_bot(bridge, bot_account)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    if body.mode == "manual":
        bot.enter_manual_mode(chat_id)
    elif body.mode == "auto":
        bot.exit_manual_mode(chat_id)
    else:
        raise HTTPException(status_code=400, detail="mode must be 'manual' or 'auto'")

    if bridge.event_bus:
        bridge.event_bus.publish("mode_change", {
            "chat_id": chat_id,
            "mode": body.mode,
        })

    return {"success": True, "chat_id": chat_id, "mode": body.mode}
