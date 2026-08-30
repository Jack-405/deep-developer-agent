"""中断取消逻辑验证。

验证 cli.session.Session.run 的协作式取消：

1. 执行中触发取消 → 返回 True、快速返回、不保存不完整回答、用户消息保留
2. 无取消事件 → 正常完成并保存回答

运行方式（无需 pytest）：

    python tests/test_interrupt.py
"""

import asyncio
import sys
import time
from pathlib import Path

# 允许直接从 tests/ 目录运行脚本（python tests/test_interrupt.py）
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cli.session as session_module
from backend.agent.stream import StreamEventType
from cli.session import Session


class FakeRenderer:
    """最小渲染器替身：实现 render_event 所需契约，记录调用不碰终端。"""

    def __init__(self):
        self.calls = []

    def begin_turn(self):
        self.calls.append("begin")

    def end_turn(self):
        self.calls.append("end")

    def status(self, text):
        self.calls.append(("status", text))

    def tool_start(self, name, summary, args):
        self.calls.append(("tool_start", name))

    def tool_end(self, name, status):
        self.calls.append(("tool_end", name))

    def text(self, text):
        self.calls.append(("text", text))

    def error(self, message):
        self.calls.append(("error", message))


class FakeAgent:
    pass


def _patch_stream(fake_stream):
    """替换 cli.session.stream_agent，返回恢复函数。"""
    original = session_module.stream_agent
    session_module.stream_agent = fake_stream
    return lambda: setattr(session_module, "stream_agent", original)


async def test_interrupt_cancels_stream_and_keeps_context():
    async def fake_stream(agent, messages, thread_id=None):
        yield {"type": StreamEventType.TEXT, "data": "part1"}
        await asyncio.sleep(10)  # 模拟长时间执行

    restore = _patch_stream(fake_stream)
    try:
        session = Session()
        renderer = FakeRenderer()
        cancel_event = asyncio.Event()

        async def fire():
            await asyncio.sleep(0.1)
            cancel_event.set()

        fire_task = asyncio.create_task(fire())

        result = await session.run(
            FakeAgent(), "帮我写代码", renderer, cancel_event=cancel_event
        )

        await fire_task
    finally:
        restore()

    assert result is True
    # 用户消息保留，不完整回答不写入
    assert session.messages == [{"role": "user", "content": "帮我写代码"}]
    # 渲染生命周期正常关闭（TEXT 事件已分发到渲染器）
    assert renderer.calls == ["begin", ("text", "part1"), "end"]


async def test_run_without_cancel_completes():
    async def fake_stream(agent, messages, thread_id=None):
        yield {"type": StreamEventType.TEXT, "data": "完整回答"}
        await asyncio.sleep(0.01)

    restore = _patch_stream(fake_stream)
    try:
        session = Session()
        renderer = FakeRenderer()
        result = await session.run(FakeAgent(), "你好", renderer)
    finally:
        restore()

    assert result is False
    assert len(session.messages) == 2
    assert session.messages[1]["role"] == "assistant"
    assert "完整回答" in session.messages[1]["content"]


async def test_interrupt_returns_quickly():
    async def fake_stream(agent, messages, thread_id=None):
        yield {"type": StreamEventType.TEXT, "data": "x"}
        await asyncio.sleep(60)  # 长时间挂起

    restore = _patch_stream(fake_stream)
    try:
        session = Session()
        renderer = FakeRenderer()
        cancel_event = asyncio.Event()

        async def fire():
            await asyncio.sleep(0.05)
            cancel_event.set()

        fire_task = asyncio.create_task(fire())

        started = time.monotonic()
        result = await session.run(
            FakeAgent(), "测试", renderer, cancel_event=cancel_event
        )
        elapsed = time.monotonic() - started

        await fire_task
    finally:
        restore()

    assert result is True
    assert elapsed < 5.0  # 未被 60s 挂起拖住


if __name__ == "__main__":
    for test in (
        test_interrupt_cancels_stream_and_keeps_context,
        test_run_without_cancel_completes,
        test_interrupt_returns_quickly,
    ):
        asyncio.run(test())
        print(f"PASS: {test.__name__}")
    print("All interrupt tests passed.")
