"""FastAPI dependency injection helpers."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from server.auth import get_current_user
from server.state import StateBridge


def get_state_bridge(request: Request) -> StateBridge:
    """Extract StateBridge from app state."""
    return request.app.state.bridge


BridgeDep = Annotated[StateBridge, Depends(get_state_bridge)]
UserDep = Annotated[dict, Depends(get_current_user)]
