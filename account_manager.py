"""多账号 Bot 管理器 — 负责加载配置、创建/启动/停止多个 XianyuLive 实例."""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from loguru import logger

from account_config import AccountConfig, MultiAccountConfig
from server.state import StateBridge, create_log_sink


class AccountManager:
    """管理多个闲鱼 Bot 实例的生命周期."""

    def __init__(self, bridge: StateBridge, config_path: str = "accounts.yaml"):
        self.bridge = bridge
        self.config_path = config_path
        self.multi_config: MultiAccountConfig = MultiAccountConfig()
        self._tasks: dict[str, asyncio.Task] = {}
        self._log_sink_ids: dict[str, int] = {}

    def load_config(self) -> list[AccountConfig]:
        """加载多账号配置."""
        self.multi_config = MultiAccountConfig.from_yaml(self.config_path)
        enabled = self.multi_config.enabled_accounts
        logger.info(f"AccountManager: 加载了 {len(enabled)} 个已启用账号")
        for acc in enabled:
            logger.info(f"  - {acc.account_id}: {acc.display_name}")

        # ── 多账号同 IP 风控警告 ──
        if len(enabled) >= 2:
            logger.warning(
                f"⚠️ 检测到 {len(enabled)} 个账号同时运行！"
                f"同一 IP 运行多账号是高危风控行为，闲鱼极易封禁。"
                f"建议：每个账号使用不同 IP（代理/VPN）运行"
            )
            # 尝试检测当前出口 IP
            try:
                import requests as req
                resp = req.get("https://api.ipify.org?format=json", timeout=5)
                ip = resp.json().get("ip", "unknown")
                logger.warning(f"⚠️ 当前出口 IP: {ip}，所有 {len(enabled)} 个账号共享此 IP")
            except Exception:
                logger.warning("⚠️ 无法检测当前出口 IP")

        return enabled

    async def start_all(self) -> None:
        """并行启动所有已启用的账号 Bot."""
        enabled = self.multi_config.enabled_accounts
        if not enabled:
            logger.warning("AccountManager: 没有启用的账号，跳过启动")
            return

        # 并行启动所有 bot（bot.main() 是长期任务，不等待完成）
        for acc in enabled:
            await self._start_single(acc)

        logger.info("AccountManager: 所有账号 Bot 已启动")

    async def _start_single(self, acc: AccountConfig) -> None:
        """启动单个账号的 Bot."""
        from main import XianyuLive

        logger.info(f"AccountManager: 启动账号 [{acc.account_id}] {acc.display_name}")

        # 创建 bot 实例
        bot = XianyuLive(
            cookies_str=acc.cookies_str,
            account_id=acc.account_id,
            display_name=acc.display_name,
            account_config=acc,
        )

        # 注入 EventBus（bot 和 API 客户端都需要）
        bot.event_bus = self.bridge.event_bus
        bot.xianyu.event_bus = self.bridge.event_bus

        # 注册到 StateBridge
        self.bridge.register_bot(acc.account_id, bot)

        # 添加账号级别的日志 sink
        log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
        sink_id = logger.add(
            create_log_sink(self.bridge.event_bus, account_id=acc.account_id),
            level=log_level,
        )
        self._log_sink_ids[acc.account_id] = sink_id

        # 启动 bot（bot.main() 是长期运行的任务）
        try:
            main_task = asyncio.create_task(bot.main())
            self.bridge.set_bot_task(acc.account_id, main_task)
            self._tasks[acc.account_id] = main_task
        except Exception as e:
            logger.error(f"AccountManager: 账号 [{acc.account_id}] 启动失败: {e}")
            self.bridge.unregister_bot(acc.account_id)
            if acc.account_id in self._log_sink_ids:
                logger.remove(self._log_sink_ids.pop(acc.account_id))

    async def stop_account(self, account_id: str) -> bool:
        """停止指定账号的 Bot."""
        bot = self.bridge.get_bot(account_id)
        if bot is None:
            logger.warning(f"AccountManager: 账号 [{account_id}] 未注册")
            return False

        logger.info(f"AccountManager: 停止账号 [{account_id}]")
        bot.request_stop()

        # 取消对应的 task
        task = self._tasks.pop(account_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 移除日志 sink
        if account_id in self._log_sink_ids:
            logger.remove(self._log_sink_ids.pop(account_id))

        # 取消注册
        self.bridge.unregister_bot(account_id)
        return True

    async def stop_all(self) -> None:
        """停止所有账号 Bot."""
        logger.info("AccountManager: 停止所有账号")
        account_ids = list(self._tasks.keys())
        for aid in account_ids:
            await self.stop_account(aid)

    async def restart_account(self, account_id: str) -> bool:
        """重启指定账号的 Bot."""
        acc = self.multi_config.get(account_id)
        if acc is None:
            logger.warning(f"AccountManager: 未找到账号配置 [{account_id}]")
            return False

        await self.stop_account(account_id)
        await self._start_single(acc)
        return True

    def get_status(self) -> dict[str, dict]:
        """获取所有账号的运行状态."""
        statuses = {}
        for acc in self.multi_config.accounts:
            bot = self.bridge.get_bot(acc.account_id)
            online = bot is not None and bot.ws is not None and not bot.ws.closed if bot else False
            statuses[acc.account_id] = {
                "account_id": acc.account_id,
                "display_name": acc.display_name,
                "enabled": acc.enabled,
                "online": online,
                "manual_mode_count": len(bot.manual_mode_conversations) if bot else 0,
                "last_heartbeat": getattr(bot, "last_heartbeat_time", 0) if bot else 0,
            }
        return statuses
