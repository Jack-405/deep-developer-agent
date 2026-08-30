"""
REPL 编排。

只负责：读输入 → 空输入/中断处理 → 命令与 Agent 分流。

命令的具体处理在 commands.py，单轮任务执行在 session.py。
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console

from cli.commands import CommandOutcome, ReplState, dispatch
from cli.history_cleanup import cleanup_conversation_history
from cli.interrupt import InterruptController
from cli.renderer import CliRenderer, _bold, _red
from cli.session import Session


logger = logging.getLogger(__name__)


async def repl(
    console: Console,
    verbose: bool,
    agent: Any,
    workspace: str,
) -> None:
    """
    CLI REPL。

    DeepDeveloper >
        ↓
    用户输入
        ↓
    命令？ ──是──→ 处理命令，继续下一轮
        ↓否
    Agent 任务（session.run）
        ↓
    流式输出（精简渲染）
        ↓
    下一轮
    """

    # 每次 CLI 启动时清理旧的会话历史归档，仅保留最近 10 个。
    # 本次运行的历史文件尚未创建，清理的是更早的归档。
    cleanup_conversation_history(workspace)

    state = ReplState(
        console=console,
        verbose=verbose,
        agent=agent,
        workspace=workspace,
        session=Session(),
    )

    # 中断控制器：Agent 执行期间把 Ctrl+C 转成取消信号，
    # 中断当前任务而不是退出程序（实现见 cli.interrupt）。
    controller = InterruptController()

    while True:

        try:

            user_input = input(
                "DeepDeveloper > "
            ).strip()

        except EOFError:

            console.print()
            break

        except KeyboardInterrupt:

            console.print("\n")
            continue

        # 忽略空输入
        if not user_input:
            continue

        # -------------------------
        # CLI 命令
        # -------------------------

        try:

            outcome = await dispatch(state, user_input)

        except KeyboardInterrupt:

            # 兜底：切换工作区等耗时命令执行中按 Ctrl+C，回到提示符而非退出
            console.print("\n")
            continue

        if outcome == CommandOutcome.EXIT:
            break

        if outcome == CommandOutcome.HANDLED:
            continue

        # -------------------------
        # Agent 任务
        # -------------------------

        renderer = CliRenderer(console, verbose=verbose)

        # 执行期间接管 Ctrl+C：中断当前任务，保留对话上下文
        controller.clear()
        controller.install()

        try:

            interrupted = await state.session.run(
                state.agent,
                user_input,
                renderer,
                cancel_event=controller.event,
            )

        except KeyboardInterrupt:

            # 防御兜底：处理器安装失败等极端情况仍能回到提示符
            interrupted = True

        except Exception:

            logger.exception(
                "Agent execution failed"
            )

            console.print(
                f"\n{_red('[error] Agent execution failed.')}\n"
            )

            interrupted = False

        finally:

            # 回到输入态：Ctrl+C 恢复默认行为（由上方 except 忽略并重提示）
            controller.uninstall()

        if interrupted:

            console.print(
                _bold(
                    "\n[interrupted] 已中断当前执行，对话上下文已保留。"
                )
            )
