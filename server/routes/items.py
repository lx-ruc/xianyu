"""Item management routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from server.deps import BridgeDep, UserDep

router = APIRouter()


@router.get("/items")
async def list_items(
    bridge: BridgeDep,
    _user: UserDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List seller's items with pagination."""
    bot = bridge.bot
    if bot is None:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    result = bot.xianyu.list_my_items(page_number=page, page_size=page_size)
    if "error" in result:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "error": result["error"]}

    data = result.get("data", {})
    card_list = data.get("cardList", [])

    items = []
    for card in card_list:
        cd = card.get("cardData", {})
        dp = cd.get("detailParams", {})
        items.append({
            "item_id": cd.get("id", ""),
            "title": dp.get("title", ""),
            "price": dp.get("soldPrice", ""),
            "pic": dp.get("pic", ""),
        })

    return {
        "items": items,
        "total": data.get("totalCount", len(items)),
        "page": page,
        "page_size": page_size,
    }


@router.get("/items/{item_id}")
async def get_item(item_id: str, bridge: BridgeDep, _user: UserDep):
    """Get item detail by ID."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot not initialized"}

    # Try cache first
    item_info = bot.context_manager.get_item_info(item_id)
    if not item_info:
        result = bot.xianyu.get_item_info(item_id)
        if "data" in result and "itemDO" in result["data"]:
            item_info = result["data"]["itemDO"]
            bot.context_manager.save_item_info(item_id, item_info)
        else:
            return {"error": "商品不存在"}

    return {"item_id": item_id, "data": item_info}


@router.post("/items/{item_id}/bump")
async def bump_item(item_id: str, bridge: BridgeDep, _user: UserDep):
    """Bump (擦亮) a single item."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot not initialized"}

    result = bot.xianyu.republish_item(item_id)
    ret = str(result.get("ret", []))
    if "SUCCESS" in ret:
        return {"success": True, "message": f"擦亮成功: {item_id}"}
    elif "POLISH_AGAIN" in ret:
        return {"success": False, "message": "该商品刚刚已擦亮，请稍后再试"}
    return {"success": False, "message": f"擦亮失败: {ret}"}


@router.post("/items/bump-all")
async def bump_all_items(bridge: BridgeDep, _user: UserDep):
    """Bump all listed items."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot not initialized"}

    import asyncio
    import random

    # Paginate to get all items (API limits page_size)
    all_cards: list[dict] = []
    page = 1
    while True:
        result = bot.xianyu.list_my_items(page_number=page, page_size=20)
        if "error" in result:
            if page == 1:
                return {"error": result["error"]}
            break
        card_list = result.get("data", {}).get("cardList", [])
        if not card_list:
            break
        all_cards.extend(card_list)
        if len(card_list) < 20:
            break
        page += 1

    if not all_cards:
        return {"success": 0, "already": 0, "fail": 0}

    success, already, fail = 0, 0, 0
    for card in all_cards:
        item_id = card.get("cardData", {}).get("id", "")
        if not item_id:
            continue
        bump_result = bot.xianyu.republish_item(item_id)
        ret = str(bump_result.get("ret", []))
        if "SUCCESS" in ret:
            success += 1
        elif "POLISH_AGAIN" in ret:
            already += 1
        else:
            fail += 1
        await asyncio.sleep(random.uniform(1.5, 3.0))

    return {"success": success, "already": already, "fail": fail}


@router.post("/items/sync")
async def sync_items(bridge: BridgeDep, _user: UserDep):
    """Sync items from Xianyu API to local database."""
    bot = bridge.bot
    if bot is None:
        return {"error": "Bot not initialized"}

    all_items = []
    page = 1
    while True:
        result = bot.xianyu.list_my_items(page_number=page, page_size=20)
        card_list = result.get("data", {}).get("cardList", [])
        if not card_list:
            break
        for card in card_list:
            item_id = card.get("cardData", {}).get("id", "")
            if item_id:
                item_result = bot.xianyu.get_item_info(item_id)
                if "data" in item_result and "itemDO" in item_result["data"]:
                    bot.context_manager.save_item_info(item_id, item_result["data"]["itemDO"])
                    all_items.append(item_id)
        if len(card_list) < 20:
            break
        page += 1

    return {"synced": len(all_items), "items": all_items}
