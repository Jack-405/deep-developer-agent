"""MCP server 注册表。

顺序即冲突改名时的优先级：先注册者保留原名，后注册者的冲突工具加
``<server>_`` 前缀。内置 godot 在前，保证 godot prompt 中硬编码的工具名
永远有效；其后为通用配置声明的 server（DEEPDEV_MCP_EXTRA，见
generic.py）。

内置 server（godot / obsidian）有复杂探测/启动逻辑，保留为代码适配器；
**新增任意 stdio MCP 无需改代码**，只需在 .env 的 ``DEEPDEV_MCP_EXTRA``
中声明启动方式（命令/参数/作用域），由 build_registry() 拼入。
"""

from __future__ import annotations

import logging

from backend.config.settings import settings
from backend.mcp.servers.base import MCPServerSpec
from backend.mcp.servers.generic import parse_mcp_extra
from backend.mcp.servers.godot.spec import GODOT_SPEC
from backend.mcp.servers.obsidian.spec import OBSIDIAN_SPEC

logger = logging.getLogger(__name__)

# 内置适配器（顺序即冲突改名优先级）
_BUILTIN_SPECS: tuple[MCPServerSpec, ...] = (GODOT_SPEC, OBSIDIAN_SPEC)


def build_registry() -> tuple[MCPServerSpec, ...]:
    """构建注册表：内置适配器 + DEEPDEV_MCP_EXTRA 声明的通用 MCP。

    任何一项构造失败都只记日志并跳过，不阻断 agent 启动。
    """
    specs: list[MCPServerSpec] = [spec for spec in _BUILTIN_SPECS]
    try:
        specs.extend(parse_mcp_extra(settings.DEEPDEV_MCP_EXTRA))
    except Exception:
        logger.exception("解析 DEEPDEV_MCP_EXTRA 失败，忽略通用 MCP 配置")
    return tuple(specs)
