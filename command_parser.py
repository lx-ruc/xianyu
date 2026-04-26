"""卖家管理指令解析器

在闲鱼聊天中通过 / 前缀指令管理商品。

支持的指令:
    /items [页码]          - 查看商品列表
    /bump <商品ID>         - 擦亮指定商品
    /bumpall               - 擦亮全部在售商品
    /search <关键词>       - 搜索同类商品
    /help                  - 查看帮助
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Command:
    """解析后的指令"""
    name: str
    args: dict


HELP_TEXT = """【商品管理指令】
/items [页码]  - 查看商品列表
/bump <商品ID>  - 擦亮商品
/bumpall  - 擦亮全部在售商品
/search <关键词>  - 搜索同类商品
/help  - 查看此帮助"""


class CommandParser:
    """解析卖家从聊天窗口发送的管理指令"""

    PREFIX = "/"

    def parse(self, message: str) -> Optional[Command]:
        """从消息中解析指令，返回 Command 或 None

        Args:
            message: 聊天消息文本

        Returns:
            解析成功的 Command，或 None（非指令消息）
        """
        text = message.strip()
        if not text.startswith(self.PREFIX):
            return None

        parts = text[len(self.PREFIX):].split(maxsplit=1)
        if not parts:
            return None

        name = parts[0].lower()
        args_text = parts[1] if len(parts) > 1 else ""
        args = self._parse_args(name, args_text)

        return Command(name=name, args=args)

    def _parse_args(self, command: str, args_text: str) -> dict:
        """根据指令类型解析参数"""
        parsers = {
            "items": self._parse_items,
            "bump": self._parse_single_id,
            "bumpall": lambda _: {},
            "search": self._parse_search,
            "help": lambda _: {},
        }
        parser = parsers.get(command, lambda _: {"raw": args_text})
        return parser(args_text)

    @staticmethod
    def _parse_items(args_text: str) -> dict:
        page = 1
        if args_text.strip().isdigit():
            page = int(args_text.strip())
        return {"page": page}

    @staticmethod
    def _parse_single_id(args_text: str) -> dict:
        return {"item_id": args_text.strip()}

    @staticmethod
    def _parse_price(args_text: str) -> dict:
        parts = args_text.strip().split(maxsplit=1)
        item_id = parts[0] if len(parts) >= 1 else ""
        price = parts[1] if len(parts) >= 2 else ""
        return {"item_id": item_id, "price": price}

    @staticmethod
    def _parse_search(args_text: str) -> dict:
        return {"keyword": args_text.strip()}

    @staticmethod
    def _parse_optional_id(args_text: str) -> dict:
        return {"item_id": args_text.strip()} if args_text.strip() else {}
