"""Configuration management routes."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.deps import BridgeDep, UserDep

router = APIRouter()

PROMPTS_DIR = Path("prompts")
PROMPT_NAMES = ["classify", "price", "tech", "default"]

# Sensitive fields that cannot be updated via API
SENSITIVE_ENV_KEYS = {"API_KEY", "COOKIES_STR", "ADMIN_USERNAME", "ADMIN_PASSWORD"}


class PromptUpdate(BaseModel):
    content: str


class SystemConfigUpdate(BaseModel):
    """Only non-sensitive fields."""
    heartbeat_interval: int | None = None
    heartbeat_jitter: int | None = None
    heartbeat_timeout: int | None = None
    token_refresh_interval: int | None = None
    token_refresh_jitter: int | None = None
    manual_mode_timeout: int | None = None
    message_expire_time: int | None = None
    simulate_human_typing: bool | None = None
    api_delay_min: float | None = None
    api_delay_max: float | None = None
    risk_cooldown_seconds: int | None = None
    toggle_keywords: str | None = None
    model_base_url: str | None = None
    model_name: str | None = None


@router.get("/prompts")
async def list_prompts(_user: UserDep):
    """List all agent prompts."""
    prompts = []
    for name in PROMPT_NAMES:
        filename = f"{name}_prompt.txt"
        filepath = PROMPTS_DIR / filename
        if not filepath.exists():
            filepath = PROMPTS_DIR / f"{name}_prompt_example.txt"

        content = ""
        last_modified = None
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            stat = filepath.stat()
            last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

        prompts.append({
            "name": name,
            "filename": filepath.name,
            "content": content,
            "last_modified": last_modified,
        })
    return prompts


@router.get("/prompts/{name}")
async def get_prompt(name: str, _user: UserDep):
    """Get a single prompt by name."""
    if name not in PROMPT_NAMES:
        raise HTTPException(status_code=404, detail="提示词不存在")

    filepath = PROMPTS_DIR / f"{name}_prompt.txt"
    if not filepath.exists():
        filepath = PROMPTS_DIR / f"{name}_prompt_example.txt"

    content = ""
    last_modified = None
    if filepath.exists():
        content = filepath.read_text(encoding="utf-8")
        stat = filepath.stat()
        last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

    return {
        "name": name,
        "filename": filepath.name,
        "content": content,
        "last_modified": last_modified,
    }


@router.put("/prompts/{name}")
async def update_prompt(name: str, body: PromptUpdate, bridge: BridgeDep, _user: UserDep):
    """Update a prompt and hot-reload it."""
    if name not in PROMPT_NAMES:
        raise HTTPException(status_code=404, detail="提示词不存在")

    # Always write to the non-example file
    filepath = PROMPTS_DIR / f"{name}_prompt.txt"
    filepath.write_text(body.content, encoding="utf-8")

    # Hot-reload in bot if available
    bot = bridge.bot
    if bot and hasattr(bot, "context_manager"):
        # Access the global bot instance to reload prompts
        try:
            from XianyuAgent import XianyuReplyBot
            # The bot module uses a global `bot` instance
            import main as main_module
            if hasattr(main_module, "bot"):
                main_module.bot._init_agents()
        except Exception:
            pass

    return {"success": True, "message": f"提示词 {name} 已更新"}


@router.get("/system")
async def get_system_config(_user: UserDep):
    """Get non-sensitive system configuration."""
    return {
        "heartbeat_interval": int(os.getenv("HEARTBEAT_INTERVAL", "15")),
        "heartbeat_jitter": int(os.getenv("HEARTBEAT_JITTER", "10")),
        "heartbeat_timeout": int(os.getenv("HEARTBEAT_TIMEOUT", "10")),
        "token_refresh_interval": int(os.getenv("TOKEN_REFRESH_INTERVAL", "7200")),
        "token_refresh_jitter": int(os.getenv("TOKEN_REFRESH_JITTER", "7200")),
        "manual_mode_timeout": int(os.getenv("MANUAL_MODE_TIMEOUT", "3600")),
        "message_expire_time": int(os.getenv("MESSAGE_EXPIRE_TIME", "300000")),
        "simulate_human_typing": os.getenv("SIMULATE_HUMAN_TYPING", "False").lower() == "true",
        "api_delay_min": float(os.getenv("API_DELAY_MIN", "1.0")),
        "api_delay_max": float(os.getenv("API_DELAY_MAX", "3.0")),
        "risk_cooldown_seconds": int(os.getenv("RISK_COOLDOWN_SECONDS", "600")),
        "toggle_keywords": os.getenv("TOGGLE_KEYWORDS", "。"),
        "model_base_url": os.getenv("MODEL_BASE_URL", ""),
        "model_name": os.getenv("MODEL_NAME", ""),
    }


@router.put("/system")
async def update_system_config(body: SystemConfigUpdate, _user: UserDep):
    """Update system configuration in .env file."""
    from dotenv import set_key

    env_path = ".env"
    updated = []

    data = body.model_dump(exclude_none=True)
    for key, value in data.items():
        env_key = key.upper()
        if env_key in SENSITIVE_ENV_KEYS:
            continue
        set_key(env_path, env_key, str(value))
        updated.append(key)
        # Also update current environment
        os.environ[env_key] = str(value)

    return {"success": True, "updated": updated, "note": "部分配置需要重启生效"}
