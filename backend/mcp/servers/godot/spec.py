"""godot-ai 的 MCPServerSpec 声明。

scope="workspace"：仅当 workspace 是 Godot 项目（存在 project.godot）时
加载，随工作区切换重建会话。现有 godot/config.py 的纯函数原样复用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.config.settings import settings
from backend.mcp.resolve import resolve_binary
from backend.mcp.servers.base import LaunchSpec, MCPServerSpec
from backend.mcp.servers.godot.config import (
    build_attach_args,
    is_godot_ai_ready,
    is_godot_workspace,
)
from backend.agent.prompts.sections.godot import GODOT_PROMPT


@dataclass(frozen=True)
class GodotSpec(MCPServerSpec):

    name: str = "godot"
    scope: str = "workspace"
    transport: str = "stdio"

    def enabled(self) -> bool:
        return settings.DEEPDEV_GODOT_ENABLED

    def ready(self) -> bool:
        return is_godot_ai_ready()

    def applicable(self, workspace: str) -> bool:
        return is_godot_workspace(workspace)

    def build_launch(self) -> LaunchSpec:
        uv = resolve_binary(
            "uv",
            explicit_path=os.environ.get("DEEPDEV_UV_BIN", ""),
            hint=(
                "未找到 uv，无法启动 godot-ai attach。\n"
                "请先安装 uv（https://docs.astral.sh/uv/）并加入 PATH，\n"
                "或设置环境变量 DEEPDEV_UV_BIN 指向 uv.exe 的完整路径。"
            ),
        )
        return LaunchSpec(
            command=uv,
            args=build_attach_args(),
            env={**os.environ},
        )

    def build_prompt(self) -> str | None:
        return GODOT_PROMPT


GODOT_SPEC = GodotSpec()
