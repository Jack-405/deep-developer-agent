"""
会话层。

持有本次 CLI 运行期间的对话上下文（内存消息列表），
并提供单轮 Agent 任务执行。

将原 cli.py 中零散的 messages 列表与 run_turn 收拢为 Session 类，
repl 不再裸持 messages 状态。

会话历史持久化：
    每次 CLI 运行对应一个稳定的 thread_id（cli-YYYYMMDD-HHMMSS），
    透传给 SummarizationMiddleware 后，被压缩裁掉的消息会自动落盘到
    <workspace>/.deepdev/conversation_history/{thread_id}.md，
    由 cli.history_cleanup 按保留策略（默认最近 10 个）自动清理。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from backend.agent.stream import stream_agent, StreamEventType

from cli.renderer import CliRenderer, render_event


class Session:
    """一次 CLI 运行期间的对话会话。

    内存消息列表保存本次 CLI 运行期间的对话上下文；
    历史归档（conversation_history）由 SummarizationMiddleware
    与 history_cleanup 负责，本类不直接落盘。
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

        # 每次 CLI 运行一个稳定的 thread_id：
        # 保证本次运行内多次摘要追加到同一个历史文件，可连续追溯。
        # 追加随机后缀，避免同一秒启动两次 CLI 时共用同一历史文件。
        self.thread_id = (
            f"cli-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            f"-{uuid.uuid4().hex[:4]}"
        )

    def clear(self) -> None:
        """清空对话上下文（切换工作区时调用）。"""
        self.messages = []

    async def run(
        self,
        agent: Any,
        user_input: str,
        renderer: CliRenderer,
        cancel_event: asyncio.Event | None = None,
    ) -> bool:
        """执行一轮 Agent 任务。

        返回 True 表示本轮被用户中断（取消）；False 表示正常完成。

        cancel_event:
            由调用方（repl）在 Agent 执行期间注入的中断标志。
            置位时协作式取消当前流式执行并尽快返回（尽力而为：
            卡死在同步阻塞中的工具调用无法强杀，超时后放行）。
        """

        self.messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        renderer.begin_turn()
        assistant_text = ""

        async def _stream() -> None:
            nonlocal assistant_text

            async for event in stream_agent(
                agent,
                self.messages,
                thread_id=self.thread_id,
            ):
                render_event(renderer, event)

                if event.get("type") == StreamEventType.TEXT:

                    assistant_text += str(
                        event.get("data", "")
                    )

        task = asyncio.create_task(_stream())

        if cancel_event is None:
            # 无中断支持：直接等待，异常原样传播
            await task
            interrupted = False
        else:
            # 与中断标志竞争：谁先完成听谁的
            cancel_task = asyncio.create_task(cancel_event.wait())

            done, _pending = await asyncio.wait(
                {task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if task in done:
                # 正常完成：重新 await 以传播 _stream 内部异常
                await task
                interrupted = False
            else:
                # 用户请求中断：取消流式执行，给短暂收敛窗口
                interrupted = True
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    # 同步阻塞无法强杀 / 已正常收敛，尽力而为
                    pass

            cancel_task.cancel()

        renderer.end_turn()

        # 被中断时不保存不完整的回答，避免污染上下文
        if assistant_text.strip() and not interrupted:

            self.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_text,
                }
            )

        return interrupted
