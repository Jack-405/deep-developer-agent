"""通用可执行文件定位工具。

多个 MCP server（godot 的 uv、obsidian 的 obsidian-mcp）都需要在宿主机上
定位一个可执行文件。deepdev 进程可能从 IDE/快捷方式启动，PATH 未必包含
所需命令，因此统一走同一套降级查找顺序。

查找顺序：

1. 显式路径（环境变量/配置显式指定，最高优先级；是文件则直接用，否则
   再按名字在 PATH 中 which 一次）
2. PATH 中的可执行文件（shutil.which）
3. 常见安装位置候选（可扩展传入）
4. 基于当前 Python 解释器推导的 Scripts 目录（pip 安装进 base/venv 的
   标准位置；对 venv 与 base 解释器都查一遍）
5. 全部失败 → 抛出带提示的 RuntimeError（由调用方决定是否降级）
"""

from __future__ import annotations

import os
import shutil
import sys


def resolve_binary(
    name: str,
    *,
    explicit_path: str = "",
    extra_candidates: tuple[str, ...] = (),
    hint: str = "",
) -> str:
    """定位名为 ``name`` 的可执行文件；找不到时给出可读错误。

    参数：
        name: 可执行文件名（如 "uv"、"obsidian-mcp"）。
        explicit_path: 显式指定的路径（环境变量/配置值）。若为空跳过。
        extra_candidates: 额外候选路径（常见安装位置），逐个检查 isfile。
        hint: 全部失败时附加在错误信息中的用户提示。

    返回：
        可执行文件的完整路径。

    异常：
        RuntimeError: 所有查找手段均未命中。
    """
    # 1. 显式指定
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        found = shutil.which(explicit_path)
        if found is not None:
            return found

    # 2. PATH
    found = shutil.which(name)
    if found is not None:
        return found

    # 3. 常见安装位置
    home = os.path.expanduser("~")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    default_candidates = (
        # Windows：用户级安装 / winget / scoop
        os.path.join(home, ".local", "bin", _exe(name)),
        os.path.join(localappdata, "Microsoft", "WinGet", "Links", _exe(name)),
        os.path.join(home, "scoop", "shims", _exe(name)),
        # Unix：用户级安装 / cargo
        os.path.join(home, ".local", "bin", name),
        os.path.join(home, ".cargo", "bin", name),
    )
    for candidate in (*default_candidates, *extra_candidates):
        if candidate and os.path.isfile(candidate):
            return candidate

    # 4. 基于当前 Python 解释器推导（pip 安装进 Scripts 目录）
    for base in {sys.prefix, sys.base_prefix}:
        candidate = os.path.join(base, "Scripts", _exe(name))
        if base and os.path.isfile(candidate):
            return candidate

    raise RuntimeError(
        f"未找到可执行文件 {name!r}。\n"
        "已尝试：PATH、显式路径、常见安装位置、Python Scripts 目录。\n"
        + (hint if hint else f"请先安装 {name} 并加入 PATH，或显式指定其完整路径。")
    )


def _exe(name: str) -> str:
    """Windows 下补齐 .exe 后缀。"""
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name
