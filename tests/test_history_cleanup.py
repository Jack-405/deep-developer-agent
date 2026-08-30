"""
conversation_history 保留策略测试（纯本地，不依赖 LLM / 网络）。

覆盖：
    1. 目录不存在 → 安全返回 0
    2. 文件数不超过 keep → 全部保留
    3. 文件数超过 keep → 仅保留最新的 keep 个
    4. thread_id 透传：stream_agent 将 thread_id 写入 LangGraph config

运行：
    .venv\\Scripts\\python.exe tests\\test_history_cleanup.py
"""

import os
import sys
import tempfile
from pathlib import Path

# 允许从任意 cwd 直接运行
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.agent.stream import stream_agent
from cli.history_cleanup import (
    DEFAULT_KEEP,
    cleanup_conversation_history,
    conversation_history_dir,
)

# asyncio 依赖 _overlapped（Winsock），在受限沙箱中可能无法导入；
# 此时跳过 thread_id 透传测试（用户本机可正常运行全部用例）。
try:
    import asyncio

    ASYNC_AVAILABLE = True
except Exception:  # noqa: BLE001 - 环境受限时跳过
    ASYNC_AVAILABLE = False

PASS = 0


def check(name: str, condition: bool) -> None:
    global PASS
    if not condition:
        raise AssertionError(f"FAIL: {name}")
    PASS += 1
    print(f"  ok - {name}")


def make_history_files(tmp: str, count: int) -> Path:
    """在临时工作区创建 count 个会话历史文件，mtime 从旧到新。"""
    history_dir = conversation_history_dir(tmp)
    history_dir.mkdir(parents=True)
    base = 1_700_000_000
    for i in range(count):
        p = history_dir / f"cli-{i:02d}.md"
        p.write_text(f"history {i}", encoding="utf-8")
        os.utime(p, (base + i, base + i))
    return history_dir


def test_no_directory() -> None:
    print("[no directory]")
    with tempfile.TemporaryDirectory() as tmp:
        check("目录不存在时返回 0", cleanup_conversation_history(tmp) == 0)
    print()


def test_within_keep_limit() -> None:
    print("[within keep limit]")
    with tempfile.TemporaryDirectory() as tmp:
        make_history_files(tmp, DEFAULT_KEEP - 1)
        removed = cleanup_conversation_history(tmp)
        check("不超过 keep 时不删除", removed == 0)
        remaining = len(list(conversation_history_dir(tmp).glob("*.md")))
        check("全部保留", remaining == DEFAULT_KEEP - 1)
    print()


def test_over_keep_limit() -> None:
    print("[over keep limit]")
    with tempfile.TemporaryDirectory() as tmp:
        total = DEFAULT_KEEP + 5
        make_history_files(tmp, total)
        removed = cleanup_conversation_history(tmp)
        check(f"{total} 个文件时删除 5 个", removed == 5)

        remaining = sorted(
            conversation_history_dir(tmp).glob("*.md"),
            key=lambda p: p.stat().st_mtime,
        )
        check("保留数量为 keep", len(remaining) == DEFAULT_KEEP)
        check(
            "保留的是最新的 keep 个",
            [p.stem for p in remaining]
            == [f"cli-{i:02d}" for i in range(5, total)],
        )
    print()


def test_memory_file_untouched() -> None:
    print("[memory file untouched]")
    with tempfile.TemporaryDirectory() as tmp:
        make_history_files(tmp, DEFAULT_KEEP + 3)
        memory_file = conversation_history_dir(tmp).parent / "memory.md"
        memory_file.write_text("runtime memory", encoding="utf-8")

        cleanup_conversation_history(tmp)

        check("memory.md 不受清理影响", memory_file.exists())
    print()


async def _test_thread_id_passthrough() -> None:
    print("[thread_id passthrough]")

    captured: dict = {}

    class FakeAgent:
        async def astream(self, inputs, **kwargs):  # noqa: ANN001
            captured.update(kwargs)
            if False:
                yield None  # pragma: no cover - 使方法成为 async generator

    async for _ in stream_agent(
        FakeAgent(),
        [{"role": "user", "content": "hi"}],
        thread_id="cli-test-123",
    ):
        pass

    config = captured.get("config")
    check(
        "thread_id 写入 configurable.thread_id",
        config is not None
        and config.get("configurable", {}).get("thread_id") == "cli-test-123",
    )

    print()


def test_thread_id_passthrough() -> None:
    if not ASYNC_AVAILABLE:
        print("[thread_id passthrough] (skipped: asyncio unavailable)")
        return
    asyncio.run(_test_thread_id_passthrough())
    print()


def main() -> None:
    test_no_directory()
    test_within_keep_limit()
    test_over_keep_limit()
    test_memory_file_untouched()
    test_thread_id_passthrough()
    print(f"PASS: {PASS} checks")


if __name__ == "__main__":
    main()
