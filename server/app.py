"""Application factory — re-exports create_app for convenience."""
from server import create_app, StateBridge

__all__ = ["create_app", "StateBridge"]
