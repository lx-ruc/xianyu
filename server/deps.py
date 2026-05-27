"""FastAPI dependency injection helpers."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, Query, Request

from server.auth import get_current_user
from server.state import StateBridge


def get_state_bridge(request: Request) -> StateBridge:
    """Extract StateBridge from app state."""
    return request.app.state.bridge


def get_bot_by_account(
    bridge: Annotated[StateBridge, Depends(get_state_bridge)],
    account_id: Optional[str] = Query(None, description="账号ID，不传则使用当前活跃账号"),
):
    """Resolve a bot instance by account_id query param.

    Returns (bot, account_id) tuple. Falls back to the active bot from StateBridge.
    """
    if account_id:
        bot = bridge.get_bot(account_id)
    else:
        account_id = bridge.active_account_id
        bot = bridge.bot

    if bot is None:
        # Return sentinel — routes should check
        return None, account_id

    return bot, account_id


def get_account_manager(request: Request):
    """Get AccountManager from app state (set during startup)."""
    return getattr(request.app.state, "account_manager", None)


BridgeDep = Annotated[StateBridge, Depends(get_state_bridge)]
UserDep = Annotated[dict, Depends(get_current_user)]
BotAccountDep = Annotated[tuple, Depends(get_bot_by_account)]
AccountManagerDep = Annotated[object, Depends(get_account_manager)]
