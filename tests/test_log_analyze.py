"""backend/logging/analyze.py 测试：事件聚合、排序、对比。

纯 stdlib 依赖，沙箱可跑；本文件自带 sys.path 引导：

    python tests/test_log_analyze.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.logging.analyze import (  # noqa: E402
    collect_startups,
    format_compare,
    format_summary,
    load_events,
)


def _write(tmp_path, lines):
    p = tmp_path / "startup.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _total_event(ts, total, phases, workspace="w1"):
    return json.dumps(
        {"ts": ts, "level": "INFO", "logger": "deepdev.startup",
         "event": "cli.startup.total", "total_ms": total,
         "phases": phases, "workspace": workspace},
        ensure_ascii=False,
    )


def test_load_events_skips_bad_lines(tmp_path):
    _write(tmp_path, [
        "not json {{{",
        _total_event("2026-08-11T01:00:00+00:00", 100.0, {"a": 10.0}),
        "",
        "{broken",
    ])
    events = load_events(tmp_path)
    assert len(events) == 1
    assert events[0]["event"] == "cli.startup.total"
    assert events[0]["_source"].endswith("startup.jsonl:2")


def test_collect_only_total_events(tmp_path):
    lines = [
        json.dumps({"event": "mcp.start", "server": "godot", "duration_ms": 50.0}),
        _total_event("2026-08-11T01:00:00+00:00", 200.0, {"mcp.collect": 150.0}),
        json.dumps({"event": "mcp.tools", "server": "obsidian", "duration_ms": 5.0}),
        _total_event("2026-08-11T02:00:00+00:00", 300.0, {"mcp.collect": 250.0}),
    ]
    _write(tmp_path, lines)
    startups = collect_startups(load_events(tmp_path))
    assert len(startups) == 2
    assert all(s.phases == {"mcp.collect": 150.0} or s.phases == {"mcp.collect": 250.0} for s in startups)
    assert startups[0].total_ms == 200.0
    assert startups[1].total_ms == 300.0


def test_collect_sorts_by_ts(tmp_path):
    _write(tmp_path, [
        _total_event("2026-08-11T03:00:00+00:00", 300.0, {}),
        _total_event("2026-08-11T01:00:00+00:00", 100.0, {}),
        _total_event("2026-08-11T02:00:00+00:00", 200.0, {}),
    ])
    startups = collect_startups(load_events(tmp_path))
    assert [s.total_ms for s in startups] == [100.0, 200.0, 300.0]
    assert [s.idx for s in startups] == [1, 2, 3]


def test_format_compare_delta():
    base = collect_startups([json.loads(_total_event(
        "2026-08-11T01:00:00+00:00", 1000.0,
        {"mcp.collect": 900.0, "agent.compile": 100.0}))])[0]
    cur = collect_startups([json.loads(_total_event(
        "2026-08-11T02:00:00+00:00", 500.0,
        {"mcp.collect": 400.0, "agent.compile": 100.0}))])[0]
    out = format_compare(base, cur)
    assert "Δtotal = -500.0 ms" in out
    assert "mcp.collect" in out and "-500.0" in out
    assert "agent.compile" in out


def test_format_compare_new_and_missing_phase():
    base = collect_startups([json.loads(_total_event(
        "2026-08-11T01:00:00+00:00", 100.0, {"old": 50.0}))])[0]
    cur = collect_startups([json.loads(_total_event(
        "2026-08-11T02:00:00+00:00", 120.0, {"new": 60.0}))])[0]
    out = format_compare(base, cur)
    assert "+新增" in out and "-消失" in out


def test_format_summary_last():
    startups = []
    for i, t in enumerate((1.0, 2.0, 3.0), 1):
        startups.append(collect_startups([json.loads(_total_event(
            f"2026-08-11T0{i}:00:00+00:00", t, {}))])[0])
    out = format_summary(startups, last=2)
    assert "1.0" not in out
    assert "2.0" in out and "3.0" in out


def test_empty_dir():
    assert collect_startups(load_events(Path("nonexistent-dir-xyz"))) == []


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    import tempfile
    for fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
            except TypeError:
                # 无 tmp_path 参数化的测试
                fn()
            passed += 1
            print(f"PASS {fn.__name__}")
    print(f"{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
