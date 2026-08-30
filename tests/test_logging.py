"""backend/logging 包测试：格式、配置、计时。

纯 stdlib 依赖（logging/json/pathlib），沙箱可跑；本文件自带 sys.path
引导，允许任意 cwd 直接运行：

    python tests/test_logging.py
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.logging import JsonlFormatter, StartupTimer, log_event, setup_logging  # noqa: E402
from backend.logging.config import LOGGER_ROOT, ConsoleFormatter  # noqa: E402


def _make_record(name, level=logging.INFO, msg="", event=None):
    record = logging.LogRecord(name, level, __file__, 1, msg, (), None)
    if event is not None:
        record.event = event
    return record


def test_jsonl_formatter_flat_events():
    fmt = JsonlFormatter()
    record = _make_record(
        "deepdev.startup",
        event={"event": "mcp.start", "server": "godot", "duration_ms": 12.3},
    )
    data = json.loads(fmt.format(record))
    assert data["event"] == "mcp.start"
    assert data["server"] == "godot"
    assert data["duration_ms"] == 12.3
    assert data["logger"] == "deepdev.startup"
    assert data["level"] == "INFO"
    assert "ts" in data
    assert data["ts"].endswith("+00:00")  # ISO 带时区


def test_jsonl_formatter_without_event():
    fmt = JsonlFormatter()
    data = json.loads(fmt.format(_make_record("deepdev.startup", msg="hello")))
    assert "event" not in data
    assert data["logger"] == "deepdev.startup"


def test_jsonl_formatter_nested_dict_serializable():
    # 确保任意嵌套 dict 字段可序列化（如 summary 的 phases）
    fmt = JsonlFormatter()
    record = _make_record(
        "deepdev.startup",
        event={"event": "x", "phases": {"a": 1.0, "b": 2.0}},
    )
    data = json.loads(fmt.format(record))
    assert data["phases"] == {"a": 1.0, "b": 2.0}


def test_console_formatter_appends_attrs():
    fmt = ConsoleFormatter("[%(levelname)s] %(name)s %(message)s")
    record = _make_record(
        "deepdev.startup",
        msg="mcp.start",
        event={"event": "mcp.start", "server": "godot", "duration_ms": 12.3},
    )
    line = fmt.format(record)
    assert line.startswith("[INFO] deepdev.startup mcp.start")
    assert "server=godot" in line
    assert "duration_ms=12.3" in line


def test_setup_logging_to_file(tmp_path):
    log_file = tmp_path / "startup.jsonl"
    setup_logging(level="INFO", log_file=log_file)
    log_event("mcp.start", server="godot", duration_ms=12.3)
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event"] == "mcp.start"
    assert data["server"] == "godot"


def test_setup_logging_idempotent(tmp_path):
    logger = logging.getLogger(LOGGER_ROOT)
    setup_logging(level="INFO", log_file=tmp_path / "a.jsonl")
    n1 = len(logger.handlers)
    setup_logging(level="INFO", log_file=tmp_path / "b.jsonl")
    n2 = len(logger.handlers)
    assert n1 == n2
    assert n2 == 2  # console + file


def test_startup_timer_phase(tmp_path):
    log_file = tmp_path / "t.jsonl"
    setup_logging(level="INFO", log_file=log_file)
    timer = StartupTimer()
    with timer.phase("mcp.start", server="godot"):
        time.sleep(0.01)
    timer.summary("startup.total")
    events = [json.loads(l) for l in log_file.read_text(encoding="utf-8").strip().splitlines()]
    phase_events = [e for e in events if e["event"] == "mcp.start"]
    assert len(phase_events) == 1
    assert phase_events[0]["duration_ms"] >= 10.0
    assert phase_events[0]["server"] == "godot"
    summary = [e for e in events if e["event"] == "startup.total"]
    assert len(summary) == 1
    assert summary[0]["total_ms"] >= 10.0
    assert "mcp.start" in summary[0]["phases"]


def test_startup_timer_checkpoint(tmp_path):
    log_file = tmp_path / "c.jsonl"
    setup_logging(level="INFO", log_file=log_file)
    timer = StartupTimer()
    time.sleep(0.005)
    timer.checkpoint("agent.model")
    time.sleep(0.005)
    timer.checkpoint("agent.compile")
    events = [json.loads(l) for l in log_file.read_text(encoding="utf-8").strip().splitlines()]
    checkpoints = [e for e in events if e["event"].startswith("agent.")]
    assert len(checkpoints) == 2
    assert checkpoints[0]["duration_ms"] >= 5.0
    assert checkpoints[1]["duration_ms"] >= 5.0


def _run_all():
    import traceback

    tests = [
        test_jsonl_formatter_flat_events,
        test_jsonl_formatter_without_event,
        test_jsonl_formatter_nested_dict_serializable,
        test_console_formatter_appends_attrs,
        test_setup_logging_to_file,
        test_setup_logging_idempotent,
        test_startup_timer_phase,
        test_startup_timer_checkpoint,
    ]
    import tempfile

    class _Tmp:
        def __init__(self, base):
            self.base = base

        def __truediv__(self, name):
            return self.base / name

    failures = 0
    tmpdir = Path(tempfile.mkdtemp(prefix="test_logging_"))
    for test in tests:
        try:
            if "tmp_path" in test.__code__.co_varnames:
                test(_Tmp(tmpdir))
            else:
                test()
            print(f"PASS {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    raise SystemExit(_run_all())
