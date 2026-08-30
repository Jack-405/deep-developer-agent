"""启动阶段计时：量化启动链路各阶段耗时。

事件经 ``deepdev.startup`` logger 发出（格式见 config.JsonlFormatter），
控制台人读 + 文件 JSONL 双路输出，供脚本聚合多轮启动对比。

两种打点方式：

- ``with timer.phase(name, **attrs):``  精确块计时（适合条件执行的局部段）。
- ``timer.checkpoint(name, **attrs)``   顺序打点，记录自上一打点以来的耗时
  （适合插入连续代码块之间，不破坏缩进）。
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

_log = logging.getLogger("deepdev.startup")


def log_event(name: str, **attrs: object) -> None:
    """发一条结构化日志事件（event 命名 + 任意 k=v 属性）。"""
    _log.info(name, extra={"event": {"event": name, **attrs}})


@dataclass
class Phase:
    """单个阶段耗时快照。"""

    name: str
    start_ms: float
    duration_ms: float
    attrs: dict[str, object] = field(default_factory=dict)


class StartupTimer:
    """启动计时器：逐段打点，结束时汇总。

    用法：
        timer = StartupTimer()
        with timer.phase("mcp.start", server="godot"):
            await session.start()
        timer.checkpoint("agent.model")   # 记录上一段（无 with 包装）耗时
        timer.summary(name="startup.total")
    """

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._last = self._start
        self._phases: list[Phase] = []

    @contextmanager
    def phase(self, name: str, **attrs: object) -> Iterator[None]:
        """上下文管理器：进入即计时，退出记录耗时并发事件。"""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            t1 = time.perf_counter()
            self._record(name, t0, t1, attrs)

    def checkpoint(self, name: str, **attrs: object) -> None:
        """顺序打点：记录自上一打点（或 timer 起点）以来的耗时。"""
        now = time.perf_counter()
        self._record(name, self._last, now, attrs)
        self._last = now

    def _record(self, name: str, t0: float, t1: float, attrs: dict[str, object]) -> None:
        start_ms = (t0 - self._start) * 1000.0
        duration_ms = (t1 - t0) * 1000.0
        self._phases.append(Phase(name, start_ms, duration_ms, dict(attrs)))
        log_event(
            name,
            start_ms=round(start_ms, 1),
            duration_ms=round(duration_ms, 1),
            **attrs,
        )

    def summary(self, name: str = "startup.total", **attrs: object) -> None:
        """记录总耗时与各阶段明细（同名阶段后者覆盖，明细见各行事件）。"""
        total_ms = (time.perf_counter() - self._start) * 1000.0
        phases = {p.name: round(p.duration_ms, 1) for p in self._phases}
        log_event(name, total_ms=round(total_ms, 1), phases=phases, **attrs)
