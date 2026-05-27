"""StateBridge and EventBus for sharing bot state with FastAPI."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Optional

from loguru import logger


class EventBus:
    """Lightweight publish/subscribe event bus using asyncio.Queue."""

    def __init__(self, buffer_size: int = 100) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._buffer: dict[str, deque] = {}
        self._buffer_size = buffer_size

    def publish(self, channel: str, data: dict[str, Any]) -> None:
        """Publish an event to a channel."""
        if channel not in self._buffer:
            self._buffer[channel] = deque(maxlen=self._buffer_size)
        self._buffer[channel].append(data)

        for queue in self._subscribers.get(channel, []):
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(data)

    def subscribe(self, channel: str) -> asyncio.Queue:
        """Subscribe to a channel, returns a Queue."""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        if channel in self._subscribers:
            try:
                self._subscribers[channel].remove(queue)
            except ValueError:
                pass

    def get_buffer(self, channel: str) -> list[dict]:
        """Get buffered events for a channel."""
        return list(self._buffer.get(channel, []))


class StateBridge:
    """Bridge between XianyuLive bot instances and FastAPI routes.

    Supports multi-account mode: bots are stored in a registry keyed by account_id.
    """

    def __init__(self) -> None:
        self.event_bus = EventBus()
        # multi-account: account_id -> XianyuLive instance
        self._bots: dict[str, Any] = {}
        self._bot_tasks: dict[str, asyncio.Task] = {}
        # backward compat: reference to the "active" bot (first registered or explicitly set)
        self._active_account_id: Optional[str] = None

    # ── Multi-account API ──────────────────────────────────────────

    def register_bot(self, account_id: str, bot: Any) -> None:
        """Register a bot instance under an account_id."""
        self._bots[account_id] = bot
        if self._active_account_id is None:
            self._active_account_id = account_id
        logger.info(f"StateBridge: registered bot for account '{account_id}'")

    def unregister_bot(self, account_id: str) -> None:
        """Remove a bot instance."""
        self._bots.pop(account_id, None)
        self._bot_tasks.pop(account_id, None)
        if self._active_account_id == account_id:
            self._active_account_id = next(iter(self._bots), None)
        logger.info(f"StateBridge: unregistered bot for account '{account_id}'")

    def get_bot(self, account_id: str) -> Optional[Any]:
        """Get a bot instance by account_id."""
        return self._bots.get(account_id)

    def get_all_bots(self) -> dict[str, Any]:
        """Get all registered bots."""
        return dict(self._bots)  # shallow copy

    def get_all_account_ids(self) -> list[str]:
        """Get all registered account ids."""
        return list(self._bots.keys())

    def set_bot_task(self, account_id: str, task: asyncio.Task) -> None:
        """Store a bot's asyncio task."""
        self._bot_tasks[account_id] = task

    def get_bot_task(self, account_id: str) -> Optional[asyncio.Task]:
        """Get a bot's asyncio task."""
        return self._bot_tasks.get(account_id)

    def is_online(self, account_id: Optional[str] = None) -> bool:
        """Check if a bot (or any bot) is online."""
        if account_id:
            bot = self._bots.get(account_id)
            return bot is not None and bot.ws is not None
        return any(bot.ws is not None for bot in self._bots.values())

    def get_bot_statuses(self) -> dict[str, dict]:
        """Get status summary for all bots."""
        result = {}
        for aid, bot in self._bots.items():
            result[aid] = {
                "online": bot.ws is not None and not bot.ws.closed if bot.ws else False,
                "ws_connected": bot.ws is not None and not bot.ws.closed if bot.ws else False,
                "last_heartbeat": getattr(bot, "last_heartbeat_time", 0),
                "manual_mode_count": len(getattr(bot, "manual_mode_conversations", set())),
            }
        return result

    # ── Backward-compat API ────────────────────────────────────────

    @property
    def bot(self) -> Optional[Any]:
        """Backward-compat: returns the active bot (or first registered)."""
        if self._active_account_id:
            return self._bots.get(self._active_account_id)
        return None

    @bot.setter
    def bot(self, value: Any) -> None:
        """Backward-compat: registers a bot under 'default' account_id."""
        self.register_bot("default", value)

    def set_bot(self, bot: Any) -> None:
        """Backward-compat: register under 'default'."""
        self.register_bot("default", bot)

    @property
    def bot_task(self) -> Optional[asyncio.Task]:
        """Backward-compat."""
        if self._active_account_id:
            return self._bot_tasks.get(self._active_account_id)
        return None

    @bot_task.setter
    def bot_task(self, value: Optional[asyncio.Task]) -> None:
        """Backward-compat."""
        if self._active_account_id and value:
            self._bot_tasks[self._active_account_id] = value

    @property
    def active_account_id(self) -> Optional[str]:
        return self._active_account_id

    @active_account_id.setter
    def active_account_id(self, account_id: str) -> None:
        if account_id in self._bots:
            self._active_account_id = account_id


def create_log_sink(event_bus: EventBus, account_id: Optional[str] = None) -> callable:
    """Create a loguru sink that publishes to EventBus.

    Args:
        event_bus: The event bus to publish to.
        account_id: If provided, events are tagged with this account_id.
    """

    def sink(message: str) -> None:
        record = message.record  # type: ignore[attr-defined]
        event_data = {
            "type": "log",
            "level": record["level"].name,
            "message": record["message"],
            "source": f"{record['name']}:{record['function']}:{record['line']}",
            "timestamp": record["time"].isoformat(),
        }
        if account_id:
            event_data["account_id"] = account_id
        event_bus.publish("log", event_data)

    return sink
