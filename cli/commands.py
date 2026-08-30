"""
命令层。

内置 CLI 命令的注册表与分发。

REPL 循环只负责读输入与异常处理，具体命令处理全部收敛到这里。
新增命令（如 cd）只需在 dispatch 中增加一个分支，不再改动 repl。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from backend.agent.factory import create_agent
from backend.memory.manager import describe_memory
from backend.workspace.manager import workspace_manager

from cli.renderer import _cyan, _red
from cli.session import Session


@dataclass
class ReplState:
    """REPL 可变共享状态。

    命令处理函数通过修改本对象来影响循环行为
    （切换工作区会重建 agent、清空会话）。
    """

    console: Console
    verbose: bool
    agent: Any
    workspace: str
    session: Session = field(default_factory=Session)


class CommandOutcome:
    """命令分发结果。"""

    NOT_A_COMMAND = "not_a_command"  # 未命中任何命令，应交给 Agent
    HANDLED = "handled"  # 已处理，继续下一轮
    EXIT = "exit"  # 退出 REPL


def print_help(console: Console) -> None:
    """显示 CLI 帮助。"""

    console.print()
    console.print("Commands:")
    console.print("  help              显示帮助")
    console.print("  exit / quit       退出")
    console.print("  workspace / pwd   显示当前工作区")
    console.print("  cd [path]         切换工作区（相对路径基于当前工作区；无参数显示当前工作区）")
    console.print("  use <path>        切换工作区（路径按进程 CWD 解析，等价于 cd）")
    console.print("  memory            显示当前工作区加载的记忆文件及内容")
    console.print("  (Ctrl+C 在 Agent 执行期间可中断当前任务，不会退出；输入提示符处按 Ctrl+C 忽略)")
    console.print()


def _show_memory(state: ReplState) -> None:
    """显示当前工作区加载的记忆文件及内容。"""

    entries = describe_memory(state.workspace)
    if not entries:
        state.console.print(_red("没有可显示的记忆信息。"))
        return

    tag_labels = {
        "global": "全局",
        "project": "项目",
        "runtime": "运行时",
    }

    state.console.print()
    state.console.print(f"记忆（工作区：{_cyan(state.workspace)}）")
    for entry in entries:
        label = tag_labels.get(entry["tag"], entry["tag"])
        state.console.print(f"  [{label}] {_cyan(entry['path'])}")

        if not entry["exists"]:
            state.console.print("      （文件不存在，跳过）")
            continue

        content = entry["content"] or ""
        lines = content.strip().splitlines()
        if not lines:
            state.console.print("      （空文件）")
            continue

        # 截断超长内容，避免刷屏
        shown = lines[:20]
        for line in shown:
            state.console.print(f"      {line}")
        if len(lines) > 20:
            state.console.print(f"      …（共 {len(lines)} 行，已截断）")
    state.console.print()


async def _switch_workspace(state: ReplState, raw_path: str) -> None:
    """切换到指定路径的工作区：更新注册表、重建 agent、清空会话。"""

    try:
        project = workspace_manager.set_current(raw_path)
        state.workspace = project["path"]
        state.session.clear()
        state.agent = await create_agent(workspace=state.workspace)
        state.console.print(f"工作区已切换：{_cyan(state.workspace)}")
    except (FileNotFoundError, NotADirectoryError) as error:
        state.console.print(_red(str(error)))


async def dispatch(state: ReplState, user_input: str) -> str:
    """分发用户输入。

    命中内置命令返回对应 CommandOutcome；
    未命中返回 NOT_A_COMMAND，由调用方交给 Agent 处理。
    """

    command = user_input.lower()

    if command in {"exit", "quit"}:

        return CommandOutcome.EXIT

    if command == "help":

        print_help(state.console)
        return CommandOutcome.HANDLED

    if command in {"workspace", "pwd"}:

        state.console.print(f"工作区：{_cyan(state.workspace)}")
        return CommandOutcome.HANDLED

    if command == "memory":

        _show_memory(state)
        return CommandOutcome.HANDLED

    if command == "cd" or command.startswith("cd "):

        raw = user_input[2:].strip()

        if not raw:

            state.console.print(f"工作区：{_cyan(state.workspace)}")
            return CommandOutcome.HANDLED

        # 相对路径基于当前工作区解析，支持 cd .. / cd subdir
        target = Path(raw)
        if not target.is_absolute():
            target = Path(state.workspace) / target

        await _switch_workspace(state, str(target))
        return CommandOutcome.HANDLED

    if command.startswith("use "):

        await _switch_workspace(state, user_input[4:].strip())
        return CommandOutcome.HANDLED

    return CommandOutcome.NOT_A_COMMAND
