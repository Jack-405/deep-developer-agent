"""obsidian-mcp 接入配置（纯函数，零第三方依赖，可沙箱测试）。

本模块只负责三件事：

1. obsidian-mcp 可执行文件定位
2. vault 路径解析
3. 启动参数构造（LaunchSpec）

设计约束：

- 为可测试性（沙箱无 pydantic-settings / asyncio），本模块**不 import
  settings**，所有配置值以显式参数传入；运行时由 spec.py 从 settings
  读取后调用。
- 路径分层：vault 与二进制路径都是机器相关配置，走 ``OBSIDIAN_BIN`` /
  ``OBSIDIAN_VAULT_PATH``（.env / 环境变量），项目文件不写绝对路径。
- v1 的 vault 解析只支持显式配置，不做自动探测（留 TODO：可探测
  Obsidian 默认 vault 位置或 workspace 内含 .obsidian/ 的目录）。
"""

from __future__ import annotations

import os

from backend.mcp.resolve import resolve_binary
from backend.mcp.servers.base import LaunchSpec


def _cargo_bin(name: str) -> str:
    """cargo install 的默认安装目录（跨平台补 .exe）。"""
    exe = f"{name}.exe" if os.name == "nt" else name
    return os.path.join(os.path.expanduser("~"), ".cargo", "bin", exe)


def resolve_obsidian_bin(bin_path: str = "") -> str:
    """定位 obsidian-mcp 可执行文件。

    ``bin_path`` 显式指定（settings.OBSIDIAN_BIN）优先；否则走通用查找
    （PATH → 常见安装位置 → Python Scripts）。找不到抛 RuntimeError。
    """
    return resolve_binary(
        "obsidian-mcp",
        explicit_path=bin_path,
        extra_candidates=(_cargo_bin("obsidian-mcp"),),
        hint=(
            "请先安装 obsidian-mcp（cargo install obsidian-mcp 或从 GitHub "
            "Releases 下载），或设置环境变量 OBSIDIAN_BIN 指向其完整路径。"
        ),
    )


def resolve_vault_path(vault_path: str = "") -> str | None:
    """解析 vault 目录。

    显式配置（settings.OBSIDIAN_VAULT_PATH）优先；为空返回 None（未配置）。
    目录不存在返回 None（v1 不做自动探测，留 TODO）。
    """
    vault = vault_path.strip()
    if not vault:
        return None
    path = os.path.abspath(os.path.expanduser(vault))
    return path if os.path.isdir(path) else None


def is_obsidian_ready(bin_path: str = "", vault_path: str = "") -> bool:
    """依赖就绪：二进制可定位 且 vault 目录已配置并存在。"""
    try:
        resolve_obsidian_bin(bin_path)
    except RuntimeError:
        return False
    return resolve_vault_path(vault_path) is not None


def build_launch(bin_path: str = "", vault_path: str = "") -> LaunchSpec:
    """构造 stdio 启动规格：``obsidian-mcp <vault>``。"""
    return LaunchSpec(
        command=resolve_obsidian_bin(bin_path),
        args=[resolve_vault_path(vault_path)],
        env={**os.environ},
    )
