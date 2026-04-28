"""WebSocket endpoints for real-time push."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()


@router.websocket("/chat")
async def ws_chat(websocket: WebSocket, level: str | None = Query(None)):
    """Real-time chat message push."""
    await websocket.accept()

    # Get StateBridge from app state
    bridge = websocket.app.state.bridge
    if bridge is None:
        await websocket.close()
        return

    queue = bridge.event_bus.subscribe("chat_message") if bridge.event_bus else None
    mode_queue = bridge.event_bus.subscribe("mode_change") if bridge.event_bus else None

    try:
        while True:
            # Check for chat events
            if queue:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await websocket.send_json(event)
                except asyncio.TimeoutError:
                    pass

            # Check for mode change events
            if mode_queue:
                try:
                    event = await asyncio.wait_for(mode_queue.get(), timeout=0.1)
                    await websocket.send_json(event)
                except asyncio.TimeoutError:
                    pass

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if queue and bridge.event_bus:
            bridge.event_bus.unsubscribe("chat_message", queue)
        if mode_queue and bridge.event_bus:
            bridge.event_bus.unsubscribe("mode_change", mode_queue)


@router.websocket("/logs")
async def ws_logs(websocket: WebSocket, level: str = Query("INFO")):
    """Real-time log push."""
    await websocket.accept()

    bridge = websocket.app.state.bridge
    if bridge is None:
        await websocket.close()
        return

    queue = bridge.event_bus.subscribe("log") if bridge.event_bus else None

    level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
    min_level = level_priority.get(level.upper(), 1)

    try:
        while True:
            if queue:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    event_level = event.get("level", "INFO")
                    if level_priority.get(event_level, 0) >= min_level:
                        await websocket.send_json(event)
                except asyncio.TimeoutError:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if queue and bridge.event_bus:
            bridge.event_bus.unsubscribe("log", queue)
