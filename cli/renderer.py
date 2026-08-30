"""
渲染层。

将流式事件渲染为简洁的终端输出。

原则（对齐成熟 coding agent CLI）：

- 工具调用只在终端底部显示单行状态条，不刷完整参数/结果
- 工具结果不回显给用户（那是给模型看的，不是给人看的）
- 最终回答流式打印
- --verbose 可查看工具完整参数（调试用）

本模块是纯展示层，不 import 任何业务模块（仅依赖 backend 的
StreamEventType 事件类型定义）。
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markup import escape

from backend.agent.stream import StreamEventType


def _cyan(text: str) -> str:
    return f"[cyan]{escape(text)}[/cyan]"


def _bold(text: str) -> str:
    return f"[bold]{escape(text)}[/bold]"


def _red(text: str) -> str:
    return f"[red]{escape(text)}[/red]"


class CliRenderer:
    """将流式事件渲染为简洁的终端输出。

    TTY：终端底部单行状态条（rich Live 覆盖刷新）；
    非 TTY：退化为精简逐行输出，避免 ANSI 噪声。
    """

    def __init__(self, console: Console, verbose: bool = False) -> None:
        self.console = console
        self.verbose = verbose
        self.use_live = console.is_terminal
        self._live: Live | None = None

    # ---------- 轮次生命周期 ----------

    def begin_turn(self) -> None:
        if self.use_live:
            self._live = Live(
                console=self.console,
                refresh_per_second=10,
                transient=False,
            )
            self._live.start()
            self._set_status("正在思考…")

    def end_turn(self) -> None:
        self._stop_live()
        self.console.print()

    def _stop_live(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    # ---------- 事件渲染 ----------

    def status(self, text: str) -> None:
        self._set_status(text)

    def tool_start(self, name: str, summary: str, args: dict[str, Any] | None) -> None:
        line = _cyan(f"[tool] {summary}")
        if self.verbose and args:
            line += f" {escape(_compact_repr(args))}"
        self._set_status(line)

    def tool_end(self, name: str, status: str) -> None:
        # 状态条由下一次事件覆盖，无需额外动作
        return

    def text(self, text: str) -> None:
        self._stop_live()
        self.console.print(text, end="", soft_wrap=True, markup=False)

    def error(self, message: str) -> None:
        self._stop_live()
        self.console.print(f"\n{_red(f'[error] {message}')}")

    def _set_status(self, text: str) -> None:
        if self._live is not None:
            self._live.update(text)
        elif text:
            self.console.print(text)


def _compact_repr(args: dict[str, Any], limit: int = 200) -> str:
    """将完整工具参数压缩成适合单行展示的字符串（--verbose 用）。"""
    text = json.dumps(args, ensure_ascii=False, default=str)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def render_event(renderer: CliRenderer, event: dict[str, Any]) -> None:
    """将 stream_agent() 产生的事件分发到渲染器。"""

    event_type = event.get("type")
    data = event.get("data")

    if event_type == StreamEventType.STATUS:
        renderer.status(str(data))

    elif event_type == StreamEventType.TOOL_START:
        if isinstance(data, dict):
            renderer.tool_start(
                str(data.get("name", "unknown")),
                str(data.get("summary", data.get("name", ""))),
                data.get("args"),
            )
        else:
            renderer.tool_start(str(data), str(data), None)

    elif event_type == StreamEventType.TOOL_END:
        if isinstance(data, dict):
            renderer.tool_end(
                str(data.get("name", "unknown")),
                str(data.get("status", "success")),
            )
        else:
            renderer.tool_end(str(data), "success")

    elif event_type == StreamEventType.TEXT:
        renderer.text(str(data))

    elif event_type == StreamEventType.CUSTOM:
        renderer.text(f"\n[custom] {data}")

    elif event_type == StreamEventType.ERROR:
        renderer.error(str(data))
