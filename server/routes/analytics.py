"""Analytics routes."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Query

from server.deps import BotAccountDep, BridgeDep, UserDep

router = APIRouter()


def _resolve_bot(bridge: BridgeDep, bot_account: BotAccountDep):
    bot, _ = bot_account
    if bot is None:
        bot = bridge.bot
    return bot


@router.get("/analytics/trend")
async def get_trend(
    bridge: BridgeDep,
    bot_account: BotAccountDep,
    _user: UserDep,
    item_id: str | None = Query(None),
    hours: int = Query(168, ge=1),
):
    """Get item analytics trend over time."""
    bot = _resolve_bot(bridge, bot_account)
    if bot is None:
        return {"trend": []}

    ctx = bot.context_manager
    trend = ctx.get_analytics_trend(item_id or "", hours)
    return {"trend": trend}


@router.get("/analytics/item-health")
async def get_item_health(bridge: BridgeDep, _user: UserDep):
    """Assess health of each item based on daily browse rate."""
    data_path = Path("data/my_items_current.json")
    if not data_path.exists():
        return {"items": []}

    with open(data_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    result = []
    for item in items:
        daily = item.get("daily_browse", 0)
        if daily >= 5:
            health = "excellent"
        elif daily >= 2:
            health = "good"
        elif daily >= 1:
            health = "warning"
        else:
            health = "critical"

        result.append({
            "item_id": item.get("item_id", ""),
            "title": item.get("title", ""),
            "daily_browse": daily,
            "browse_cnt": item.get("browseCnt", 0),
            "want_cnt": item.get("wantCnt", 0),
            "days": item.get("days", 0),
            "health": health,
        })

    return {"items": result}


@router.get("/analytics/competitors")
async def get_competitors(
    _user: UserDep,
    keyword: str | None = Query(None),
):
    """Get competitor data from locally stored JSON files."""
    data_dir = Path("data")
    results = []

    for fp in data_dir.glob("competitor_*.json"):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        file_keyword = fp.stem.replace("competitor_", "")
        items = data if isinstance(data, list) else data.get("items", [])

        for i, item in enumerate(items):
            title = item.get("title", "")
            if keyword and keyword not in title and keyword not in file_keyword:
                continue
            results.append({
                "keyword": file_keyword,
                "rank": i + 1,
                "title": title,
                "views": item.get("viewCount", item.get("views", 0)),
                "wants": item.get("wantCount", item.get("wants", 0)),
                "price": item.get("price", ""),
            })

    return {"competitors": results}


@router.get("/analytics/ranking")
async def get_ranking(bridge: BridgeDep, _user: UserDep):
    """Get search ranking for seller's items."""
    data_dir = Path("data")
    my_items_path = data_dir / "my_items_current.json"

    if not my_items_path.exists():
        return {"rankings": []}

    with open(my_items_path, "r", encoding="utf-8") as f:
        my_items = json.load(f)

    rankings = []
    for fp in data_dir.glob("competitor_*.json"):
        keyword = fp.stem.replace("competitor_", "")

        with open(fp, "r", encoding="utf-8") as f:
            competitors = json.load(f)
        comp_list = competitors if isinstance(competitors, list) else competitors.get("items", [])

        my_in_keyword = []
        for my_item in my_items:
            title = my_item.get("title", "")
            if any(kw in title for kw in keyword.split()):
                my_in_keyword.append({
                    "item_id": my_item.get("item_id", ""),
                    "title": title,
                    "views": my_item.get("browseCnt", 0),
                    "daily_browse": my_item.get("daily_browse", 0),
                })

        if my_in_keyword:
            rankings.append({
                "keyword": keyword,
                "my_items": my_in_keyword,
                "competitors_count": len(comp_list),
            })

    return {"rankings": rankings}
