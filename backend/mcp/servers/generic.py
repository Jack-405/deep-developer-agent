"""通用（配置驱动）MCP server 声明。

内置适配器（godot / obsidian）的探测与启动逻辑复杂，保留为代码；
其它任意 stdio MCP server 只需在 ``DEEPDEV_MCP_EXTRA``（.env）中声明
启动方式即可接入，**无需修改任何代码**。

本模块零第三方依赖（仅 stdlib + base.py 协议），可沙箱单测。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.mcp.resolve import resolve_binary
from backend.mcp.servers.base import LaunchSpec, MCPServerSpec

logger = logging.getLogger(__name__)

# 项目根目录：backend/mcp/servers/generic.py 向上 3 级
BASE_DIR = Path(__file__).resolve().parents[3]

VALID_SCOPES = ("workspace", "global")


@dataclass(frozen=True)
class GenericSpec:
    """从配置字典构建的通用 MCP server 声明。

    对应 ``DEEPDEV_MCP_EXTRA`` 中每一项的结构：:

        {
            "name": "my-mcp",
            "scope": "global",          # 可选，默认 global
            "command": "npx",           # 必填：可执行文件（绝对路径或 PATH 名）
            "args": ["-y", "@some/mcp-server"],
            "env": {"KEY": "value"},    # 可选：附加环境变量
            "enabled": true,            # 可选，默认 true
            "prompt": "引导文本",       # 可选：内联提示词
            "prompt_file": "path.md",   # 可选：提示词文件（相对项目根）
        }

    ``transport`` 固定为 stdio（一期仅支持此传输）。
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    scope: str = "global"
    env: dict[str, str] = field(default_factory=dict)
    # 注意：不能用 `enabled` 作为字段名——会与协议方法 enabled() 同名冲突
    # （dataclass 生成的实例属性会遮蔽方法）。配置键仍是 "enabled"，
    # 在 _build_one() 里映射到本字段。
    is_enabled: bool = True
    prompt: str | None = None
    prompt_file: str | None = None
    transport: str = "stdio"

    # ------------------------------------------------------------------
    # MCPServerSpec 协议
    # ------------------------------------------------------------------

    def enabled(self) -> bool:
        return self.is_enabled

    def ready(self) -> bool:
        """command 可定位即可认为就绪（不拉起进程，避免阻塞启动）。"""
        try:
            resolve_binary(self.command, explicit_path=self.command)
            return True
        except RuntimeError:
            return False

    def applicable(self, workspace: str) -> bool:
        # workspace 作用域不做自动探测（配置驱动）；是否启用由
        # enabled + ready 决定，此处恒 True。
        return True

    def build_launch(self) -> LaunchSpec:
        return LaunchSpec(
            command=self.command,
            args=list(self.args),
            # 合并宿主环境变量 + 配置附加项（配置项优先）
            env={**os.environ, **self.env},
        )

    def build_prompt(self) -> str | None:
        if self.prompt and self.prompt.strip():
            return self.prompt
        if self.prompt_file:
            return _read_prompt_file(self.prompt_file)
        return None


def _read_prompt_file(rel_path: str) -> str | None:
    """读取相对项目根的提示词文件；失败记日志返回 None（不阻断）。"""
    path = Path(rel_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("读取 MCP 提示词文件失败，忽略: %s", path)
        return None


def parse_mcp_extra(raw: str) -> list[GenericSpec]:
    """把 ``DEEPDEV_MCP_EXTRA`` 的 JSON 字符串解析为 GenericSpec 列表。

    解析/校验失败的项只记日志并跳过，不抛异常、不阻断启动。
    """
    if not raw or not raw.strip():
        return []

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("DEEPDEV_MCP_EXTRA 不是合法 JSON，忽略: %s", exc)
        return []

    if not isinstance(items, list):
        logger.warning("DEEPDEV_MCP_EXTRA 应为 JSON 数组，忽略")
        return []

    specs: list[GenericSpec] = []
    for item in items:
        spec = _build_one(item)
        if spec is not None:
            specs.append(spec)
    return specs


def _build_one(item: object) -> GenericSpec | None:
    if not isinstance(item, dict):
        logger.warning("DEEPDEV_MCP_EXTRA 项不是对象，跳过: %r", item)
        return None

    name = str(item.get("name", "")).strip()
    command = str(item.get("command", "")).strip()
    if not name or not command:
        logger.warning(
            "DEEPDEV_MCP_EXTRA 项缺少 name/command，跳过: %r", item
        )
        return None

    scope = str(item.get("scope", "global")).strip() or "global"
    if scope not in VALID_SCOPES:
        logger.warning(
            "DEEPDEV_MCP_EXTRA 项 %s scope=%r 非法（%s），跳过",
            name,
            scope,
            "/".join(VALID_SCOPES),
        )
        return None

    args = item.get("args") or []
    if not isinstance(args, list):
        logger.warning("DEEPDEV_MCP_EXTRA 项 %s args 应为数组，跳过", name)
        return None

    env = item.get("env") or {}
    if not isinstance(env, dict):
        logger.warning("DEEPDEV_MCP_EXTRA 项 %s env 应为对象，跳过", name)
        return None

    return GenericSpec(
        name=name,
        command=command,
        args=[str(a) for a in args],
        scope=scope,
        env={str(k): str(v) for k, v in env.items()},
        is_enabled=bool(item.get("enabled", True)),
        prompt=str(item["prompt"]) if item.get("prompt") else None,
        prompt_file=str(item["prompt_file"]) if item.get("prompt_file") else None,
    )