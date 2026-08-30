"""deepdev 日志配置：控制台人读 + 文件 JSONL 两路输出。

- 控制台：人类可读摘要（``[LEVEL] logger message k=v ...``），默认级别 INFO。
- 文件：JSON Lines，每行一个结构化事件，供脚本聚合（如多次启动耗时对比）。

事件结构（JSONL 每行）：

    {"ts": "...", "level": "INFO", "logger": "deepdev.startup",
     "event": "mcp.start", "server": "godot", "duration_ms": 1540.2}

事件字段通过 ``logging.LogRecord`` 的 ``extra={"event": {...}}`` 传入，
``JsonlFormatter`` 负责把 dict 平铺进 JSON 行（``event`` 键保留事件名）。

零第三方依赖，仅 stdlib ``logging`` / ``json``。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER_ROOT = "deepdev"

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class JsonlFormatter(logging.Formatter):
    """把日志记录格式化为单行 JSON（JSONL）。"""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        payload = getattr(record, "event", None)
        if isinstance(payload, dict):
            entry.update(payload)
        elif payload is not None:
            entry["event"] = payload
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """控制台人读格式：message 后追加 event 的 ``k=v`` 明细。"""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        payload = getattr(record, "event", None)
        if isinstance(payload, dict):
            kv = " ".join(
                f"{k}={v}" for k, v in payload.items() if k != "event"
            )
            if kv:
                line = f"{line} {kv}"
        return line


def setup_logging(level: str = "INFO", log_file: str | Path | None = None) -> None:
    """配置 ``deepdev.*`` logger（幂等，可重复调用）。

    参数：
        level: 控制台级别（DEBUG/INFO/WARNING/ERROR，默认 INFO）。
        log_file: JSONL 输出文件路径；None/空串 = 只打控制台。
    """
    level_no = _LEVELS.get(str(level).upper(), logging.INFO)
    root = logging.getLogger(LOGGER_ROOT)
    # 根 logger 放行全部级别，由各 handler 自行过滤；不向 stdlib root
    # 传播（避免与三方库/CLI 自身日志交叉污染）。
    root.setLevel(logging.DEBUG)
    root.propagate = False

    # 幂等：先清空旧 handler，防止重复 setup 叠加输出。
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level_no)
    console.setFormatter(ConsoleFormatter("[%(levelname)s] %(name)s %(message)s"))
    root.addHandler(console)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonlFormatter())
        root.addHandler(file_handler)
