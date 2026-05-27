"""多账号配置数据模型与加载器."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class AccountConfig:
    """单个闲鱼账号配置."""

    account_id: str          # 唯一标识，如 "main"、"shop_b"
    display_name: str        # 显示名称，如 "主账号-数码店"
    cookies_str: str         # 闲鱼 Cookie 字符串
    enabled: bool = True     # 是否启用

    # 可选：账号级别覆盖（不填则用全局配置）
    toggle_keywords: Optional[str] = None
    auto_delivery: Optional[bool] = None
    auto_rate: Optional[bool] = None
    rate_content: Optional[str] = None
    admin_user_ids: Optional[list[str]] = None

    # db_path 可选，不填则自动生成 data/chat_history_{account_id}.db
    db_path: Optional[str] = None


@dataclass
class MultiAccountConfig:
    """多账号总配置."""

    accounts: list[AccountConfig] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str = "accounts.yaml") -> MultiAccountConfig:
        """从 YAML 文件加载多账号配置."""
        yaml_path = Path(path)
        if not yaml_path.exists():
            return cls()

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        accounts = []
        for item in data.get("accounts", []):
            accounts.append(AccountConfig(
                account_id=item["account_id"],
                display_name=item["display_name"],
                cookies_str=item["cookies_str"],
                enabled=item.get("enabled", True),
                toggle_keywords=item.get("toggle_keywords"),
                auto_delivery=item.get("auto_delivery"),
                auto_rate=item.get("auto_rate"),
                rate_content=item.get("rate_content"),
                admin_user_ids=item.get("admin_user_ids"),
                db_path=item.get("db_path"),
            ))

        return cls(accounts=accounts)

    @property
    def enabled_accounts(self) -> list[AccountConfig]:
        """返回所有启用的账号."""
        return [a for a in self.accounts if a.enabled]

    def get(self, account_id: str) -> Optional[AccountConfig]:
        """按 ID 查找账号."""
        for a in self.accounts:
            if a.account_id == account_id:
                return a
        return None
