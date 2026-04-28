"""StateBridge and EventBus for sharing bot state with FastAPI."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from loguru import logger


class EventBus:
    """Lightweight publish/subscribe event bus using asyncio.Queue."""

    def __init__(self, buffer_size: int = 100) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._buffer: dict[str, deque] = {}
        self._buffer_size = buffer_size

    def publish(self, channel: str, data: dict[str, Any]) -> None:
        """Publish an event to a channel."""
        # Buffer the event
        if channel not in self._buffer:
            self._buffer[channel] = deque(maxlen=self._buffer_size)
        self._buffer[channel].append(data)

        # Send to all subscribers
        for queue in self._subscribers.get(channel, []):
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                # Drop oldest if full
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
    """Bridge between XianyuLive bot instance and FastAPI routes."""

    def __init__(self) -> None:
        self.bot: Any = None  # XianyuLive instance
        self.event_bus: EventBus = EventBus()
        self.bot_task: asyncio.Task | None = None

    def set_bot(self, bot: Any) -> None:
        """Set the bot instance reference."""
        self.bot = bot
        logger.info("StateBridge: bot instance registered")

    def is_online(self) -> bool:
        """Check if bot is online."""
        if self.bot is None:
            return False
        return self.bot.ws is not None


def create_log_sink(event_bus: EventBus) -> callable:
    """Create a loguru sink that publishes to EventBus."""

    def sink(message: str) -> None:
        record = message.record  # type: ignore[attr-defined]
        event_bus.publish("log", {
            "type": "log",
            "level": record["level"].name,
            "message": record["message"],
            "source": f"{record['name']}:{record['function']}:{record['line']}",
            "timestamp": record["time"].isoformat(),
        })

    return sink
