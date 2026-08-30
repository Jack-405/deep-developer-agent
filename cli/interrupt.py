"""
中断控制层。

把终端 Ctrl+C（SIGINT）从"抛 KeyboardInterrupt 打断事件循环"改造为
"设置异步中断标志"，供 REPL 在 Agent 执行期间以协作方式取消任务。

职责边界（模块化约束）：
- 本模块只负责「信号 ↔ asyncio 标志」的转换，
  不感知 Agent / REPL / 渲染，不持有会话状态。
- 平台差异（Windows 无 loop.add_signal_handler）收敛在本模块。

用法（由 repl.py 接线）：

    controller = InterruptController()

    # Agent 执行期间：接管 Ctrl+C
    controller.clear()
    controller.install()
    try:
        interrupted = await session.run(..., cancel_event=controller.event)
    finally:
        controller.uninstall()   # 回到输入态，Ctrl+C 恢复默认行为

注意：
- install() / uninstall() 必须成对调用（repl 用 try/finally 保证）。
- signal.signal 只能在主线程调用；本模块假定在 REPL 主线程使用。
- 输入提示符（input 阻塞）阶段不要安装：此时没有运行中的事件循环，
  处理器内 get_running_loop() 会失败，Ctrl+C 应维持默认 KeyboardInterrupt，
  由 repl 的 except KeyboardInterrupt 忽略并重新提示。
"""

from __future__ import annotations

import asyncio
import logging
import signal
from types import FrameType
from typing import Optional

logger = logging.getLogger(__name__)


class InterruptController:
    """终端中断（Ctrl+C / SIGINT）→ asyncio 标志的转换器。

    install() 之后，Ctrl+C 不再抛出 KeyboardInterrupt，
    而是通过事件循环调度把内部事件置位；Agent 执行任务
    由调用方用 asyncio.wait 竞争该事件实现协作式取消。
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._installed = False

    # ---------- 信号生命周期 ----------

    def install(self) -> None:
        """注册 SIGINT 处理器（幂等）。失败时降级为不接管。"""
        if self._installed:
            return
        try:
            signal.signal(signal.SIGINT, self._on_sigint)
            self._installed = True
        except (ValueError, OSError) as exc:
            # 非主线程 / 平台不支持等场景：Ctrl+C 维持默认行为
            logger.warning("Failed to install SIGINT handler: %s", exc)

    def uninstall(self) -> None:
        """恢复默认 SIGINT 处理（幂等）。"""
        if not self._installed:
            return
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        except (ValueError, OSError) as exc:
            logger.warning("Failed to restore SIGINT handler: %s", exc)
        finally:
            self._installed = False

    # ---------- 标志操作 ----------

    @property
    def event(self) -> asyncio.Event:
        """中断标志事件，供 asyncio.wait 竞争。"""
        return self._event

    def clear(self) -> None:
        """复位标志（每轮 Agent 执行前调用）。"""
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()

    # ---------- 内部 ----------

    def _on_sigint(self, signum: int, frame: Optional[FrameType]) -> None:
        """SIGINT 处理器：请求中断（跨线程安全）。

        Windows 无 add_signal_handler；信号处理器在主线程执行，
        通过 call_soon_threadsafe 把置位调度进事件循环。
        事件循环未运行（如阻塞在 input()）时忽略。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.call_soon_threadsafe(self._event.set)
