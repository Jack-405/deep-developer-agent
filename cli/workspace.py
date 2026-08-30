"""
工作区解析与启动横幅。

按优先级确定工作区：--workspace > 启动时终端所在目录（CWD）> 注册表。

本模块是唯一依赖 backend.workspace.manager 的 CLI 模块。
将来调整工作区解析优先级，只改这里。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from backend.workspace.manager import workspace_manager

from cli.renderer import _bold, _cyan, _red


def _default_workspace() -> Path:
    """默认工作区：启动时终端所在目录。"""
    return Path.cwd().resolve()


def resolve_workspace(args: argparse.Namespace, console: Console) -> str:
    """按优先级确定工作区：--workspace > CWD > 注册表。"""
    if args.workspace:
        try:
            return workspace_manager.set_current(args.workspace)["path"]
        except (FileNotFoundError, NotADirectoryError) as error:
            console.print(_red(f"工作区无效：{error}"))
            sys.exit(1)

    # 默认工作区 = 启动时终端所在目录
    default_workspace = _default_workspace()
    if default_workspace.exists() and default_workspace.is_dir():
        return workspace_manager.set_current(str(default_workspace))["path"]

    # 回退：注册表记录（CWD 异常时兜底）
    current = workspace_manager.get_current()
    if current:
        return current

    while True:
        console.print("未找到可用的工作区。")
        answer = input("输入工作区路径（输入 quit 退出）：").strip()
        if not answer:
            continue
        if answer.lower() in {"quit", "exit"}:
            sys.exit(0)
        try:
            return workspace_manager.set_current(answer)["path"]
        except (FileNotFoundError, NotADirectoryError) as error:
            console.print(_red(str(error)))


def print_banner(console: Console, workspace: str) -> None:
    """显示 CLI 启动信息。"""

    console.print()
    console.print(_bold("DeepDeveloper") + " - AI-powered development assistant (CLI)")
    console.print(f"工作区：{_cyan(workspace)}（文件访问仅限此目录）")
    console.print("输入 help 查看帮助，exit 退出。")
    console.print()
