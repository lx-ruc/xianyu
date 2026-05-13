"""Order management routes."""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from server.deps import BridgeDep, UserDep

router = APIRouter()

ENV_PATH = Path(__file__).parent.parent.parent / ".env"


def _update_env(key: str, value: str) -> None:
    """Persist a key=value pair to .env file (best-effort)."""
    if not ENV_PATH.exists():
        return
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    if f"{key}=" in content:
        new_content = re.sub(rf"{key}=.*", f"{key}={value}", content)
    else:
        new_content = content.rstrip() + f"\n{key}={value}\n"
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)


@router.get("/orders")
async def list_orders(
    bridge: BridgeDep,
    _user: UserDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List recent orders with pagination."""
    bot = bridge.bot
    if bot is None:
        return {"orders": [], "total": 0, "page": page, "page_size": page_size}

    offset = (page - 1) * page_size
    orders = bot.context_manager.get_recent_orders(limit=page_size, offset=offset)
    stats = bot.context_manager.get_order_stats()

    return {
        "orders": orders,
        "total": stats["total"],
        "page": page,
        "page_size": page_size,
    }


@router.get("/orders/stats")
async def get_order_stats(bridge: BridgeDep, _user: UserDep):
    """Get order statistics."""
    bot = bridge.bot
    if bot is None:
        return {
            "total": 0, "pending": 0, "delivered": 0,
            "failed": 0, "rated": 0, "rate_failed": 0,
            "today_count": 0, "today_delivered": 0,
        }

    return bot.context_manager.get_order_stats()


@router.post("/orders/{order_id}/deliver")
async def manual_deliver(order_id: str, bridge: BridgeDep, _user: UserDep):
    """Manually trigger virtual delivery for an order."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot not initialized"}

    result = bot.xianyu.virtual_delivery(order_id)
    ret = str(result.get("ret", []))

    if "SUCCESS" in ret:
        bot.context_manager.save_order(
            order_id, user_id="", status="delivered", delivery_result=ret,
        )
        return {"success": True, "message": f"发货成功: {order_id}"}

    bot.context_manager.save_order(
        order_id, user_id="", status="failed", delivery_result=ret,
    )
    return {"success": False, "message": f"发货失败: {ret}"}


@router.post("/orders/{order_id}/rate")
async def manual_rate(order_id: str, bridge: BridgeDep, _user: UserDep):
    """Manually trigger rating for an order."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot not initialized"}

    content = getattr(bot, "rate_content", "好买家，交易愉快")
    result = bot.xianyu.rate_buyer(order_id, content)
    ret = str(result.get("ret", []))

    if "SUCCESS" in ret:
        bot.context_manager.save_order(
            order_id, user_id="", status="rated", delivery_result=ret,
        )
        return {"success": True, "message": f"评价成功: {order_id}"}

    bot.context_manager.save_order(
        order_id, user_id="", status="rate_failed", delivery_result=ret,
    )
    return {"success": False, "message": f"评价失败: {ret}"}


class OrderConfigResponse(BaseModel):
    auto_delivery: bool = False
    auto_rate: bool = False
    rate_content: str = "好买家，交易愉快"


class OrderConfigRequest(BaseModel):
    auto_delivery: bool | None = None
    auto_rate: bool | None = None
    rate_content: str | None = None


@router.get("/orders/config")
async def get_order_config(bridge: BridgeDep, _user: UserDep):
    """Get order automation configuration."""
    bot = bridge.bot
    auto_delivery = os.getenv("AUTO_DELIVERY", "false").lower() == "true"
    auto_rate = os.getenv("AUTO_RATE", "false").lower() == "true"
    rate_content = os.getenv("RATE_CONTENT", "好买家，交易愉快")

    if bot is not None:
        auto_delivery = bot.auto_delivery
        auto_rate = bot.auto_rate
        rate_content = bot.rate_content

    return {
        "auto_delivery": auto_delivery,
        "auto_rate": auto_rate,
        "rate_content": rate_content,
    }


@router.post("/orders/config")
async def set_order_config(
    req: OrderConfigRequest,
    bridge: BridgeDep,
    _user: UserDep,
):
    """Update order automation configuration."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot not initialized"}

    if req.auto_delivery is not None:
        bot.auto_delivery = req.auto_delivery
        _update_env("AUTO_DELIVERY", "true" if req.auto_delivery else "false")

    if req.auto_rate is not None:
        bot.auto_rate = req.auto_rate
        _update_env("AUTO_RATE", "true" if req.auto_rate else "false")

    if req.rate_content is not None:
        bot.rate_content = req.rate_content
        _update_env("RATE_CONTENT", req.rate_content)

    return {
        "success": True,
        "message": "配置已更新",
        "auto_delivery": bot.auto_delivery,
        "auto_rate": bot.auto_rate,
        "rate_content": bot.rate_content,
    }
