"""
CLI 入口。

只负责：参数解析 → 工作区解析 → 组装 agent → 启动 REPL。

运行方式：

    python -m cli            # 推荐
    python -m cli.main
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from rich.console import Console

from backend.agent.factory import create_agent
from backend.config.settings import settings
from backend.logging import StartupTimer, setup_logging
from backend.mcp.client import mcp_manager

from cli.renderer import _red
from cli.repl import repl
from cli.workspace import print_banner, resolve_workspace


logger = logging.getLogger(__name__)


async def main() -> None:
    """CLI 入口。"""

    parser = argparse.ArgumentParser(
        description="DeepDeveloper CLI",
    )
    parser.add_argument(
        "--workspace",
        help="工作区目录路径（不指定时默认启动时的当前终端目录）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示工具完整参数（调试用）",
    )
    args = parser.parse_args()

    # 日志在参数解析后立即初始化（量化启动全过程；控制台 + 可选 JSONL 文件）
    setup_logging(
        level=settings.DEEPDEV_LOG_LEVEL,
        log_file=settings.DEEPDEV_LOG_FILE or None,
    )

    console = Console()
    timer = StartupTimer()

    workspace = resolve_workspace(args, console)
    timer.checkpoint("cli.workspace")
    print_banner(console, workspace)

    try:

        agent = await create_agent(workspace=workspace)

    except Exception:

        logger.exception(
            "Failed to create agent"
        )

        console.print(
            _red("[error] Failed to create agent.")
        )

        return

    timer.checkpoint("cli.agent")
    timer.summary(name="cli.startup.total", workspace=workspace)

    try:
        await repl(console, args.verbose, agent, workspace)
    finally:
        # REPL 级单例：退出时统一回收所有 MCP 子进程（幂等，安全）
        await mcp_manager.shutdown()

    console.print("Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
