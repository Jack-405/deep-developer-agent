"""obsidian-mcp 的 MCPServerSpec 声明。

scope="global"：vault 是与 workspace 无关的固定目录，app 启动即加载，
不随工作区切换而重建。
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.config.settings import settings
from backend.mcp.servers.base import LaunchSpec, MCPServerSpec
from backend.mcp.servers.obsidian.config import (
    build_launch as _build_launch,
    is_obsidian_ready as _is_obsidian_ready,
)
from backend.agent.prompts.sections.obsidian import OBSIDIAN_PROMPT


@dataclass(frozen=True)
class ObsidianSpec(MCPServerSpec):

    name: str = "obsidian"
    scope: str = "global"
    transport: str = "stdio"

    def enabled(self) -> bool:
        return settings.OBSIDIAN_ENABLED

    def ready(self) -> bool:
        return _is_obsidian_ready(
            bin_path=settings.OBSIDIAN_BIN,
            vault_path=settings.OBSIDIAN_VAULT_PATH,
        )

    def applicable(self, workspace: str) -> bool:
        # global 作用域：与 workspace 无关，只要 enabled+ready 即可加载
        return True

    def build_launch(self) -> LaunchSpec:
        return _build_launch(
            bin_path=settings.OBSIDIAN_BIN,
            vault_path=settings.OBSIDIAN_VAULT_PATH,
        )

    def build_prompt(self) -> str | None:
        return OBSIDIAN_PROMPT


OBSIDIAN_SPEC = ObsidianSpec()
