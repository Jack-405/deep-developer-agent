"""启动耗时聚合与对比工具（纯 stdlib，零第三方依赖）。

聚合单元 = 一条 ``cli.startup.total`` 事件（含 ``total_ms`` + ``phases``
全量画像，一次启动写一条）。按 ts 排序后支持任意两次启动对比，
用于量化/验证启动优化效果（如并行 MCP 启动、uv --no-sync）。

用法：
    python -m backend.logging.analyze                 # 全部启动摘要
    python -m backend.logging.analyze --last 5        # 只看最近 5 次
    python -m backend.logging.analyze --compare 1 2   # 对比第 1 与第 2 次启动
    python -m backend.logging.analyze --json          # 输出 JSON（脚本/CI 用）
    python -m backend.logging.analyze --dir X         # 指定日志目录（默认 logs/）
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOTAL_EVENT = "cli.startup.total"


@dataclass
class Startup:
    """一次启动的耗时画像（来自一条 cli.startup.total 事件）。"""

    idx: int
    ts: str
    workspace: str
    total_ms: float
    phases: dict[str, float] = field(default_factory=dict)
    source: str = ""


def load_events(log_dir: str | Path) -> list[dict[str, Any]]:
    """读取目录下所有 *.jsonl 的行事件；坏行跳过并静默计数。

    每行 JSON 附 ``_source``（文件:行号）便于排查。
    """
    events: list[dict[str, Any]] = []
    root = Path(log_dir)
    if not root.is_dir():
        return events
    for path in sorted(root.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            # 读取失败（权限/被占用/坏编码，如中断写入残留）跳过该文件
            continue
        for lineno, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                data["_source"] = f"{path}:{lineno}"
                events.append(data)
    return events


def collect_startups(events: list[dict[str, Any]]) -> list[Startup]:
    """过滤 ``cli.startup.total`` 事件并按 ts 升序编号为 Startup 列表。"""
    items = [
        e for e in events
        if e.get("event") == TOTAL_EVENT and e.get("total_ms") is not None
    ]
    items.sort(key=lambda e: str(e.get("ts", "")))
    startups: list[Startup] = []
    for i, e in enumerate(items, 1):
        phases = e.get("phases")
        try:
            total_ms = float(e["total_ms"])
        except (TypeError, ValueError):
            # 数值异常（正常事件流不会出现），防御性跳过该条
            continue
        startups.append(
            Startup(
                idx=i,
                ts=str(e.get("ts", "")),
                workspace=str(e.get("workspace", "")),
                total_ms=total_ms,
                phases=(
                    {str(k): float(v) for k, v in phases.items()}
                    if isinstance(phases, dict)
                    else {}
                ),
                source=str(e.get("_source", "")),
            )
        )
    return startups


def format_summary(startups: list[Startup], last: int | None = None) -> str:
    """纯文本摘要表（不用 rich，保持零依赖）。"""
    sel = startups[-last:] if last and last > 0 else startups
    if not sel:
        return "（无启动记录）"
    lines = [
        f"{'#':>3}  {'total(ms)':>10}  {'workspace':<24}  ts",
        "-" * 88,
    ]
    for s in sel:
        lines.append(
            f"{s.idx:>3}  {s.total_ms:>10.1f}  {s.workspace:<24}  {s.ts}"
        )
    return "\n".join(lines)


def format_compare(baseline: Startup, current: Startup) -> str:
    """对比两次启动：逐 phase 列 delta（正 = 变慢，负 = 变快）。"""
    keys = list(dict.fromkeys([*baseline.phases, *current.phases]))
    lines = [
        f"对比：#{baseline.idx}（基线，total={baseline.total_ms:.1f}ms）"
        f" vs #{current.idx}（total={current.total_ms:.1f}ms）",
        f"Δtotal = {current.total_ms - baseline.total_ms:+.1f} ms",
        "",
        f"{'phase':<24} {'基线(ms)':>10} {'当前(ms)':>10} {'Δ(ms)':>10}",
        "-" * 60,
    ]
    for k in keys:
        a = baseline.phases.get(k)
        b = current.phases.get(k)
        if a is None:
            lines.append(f"{k:<24} {'—':>10} {b:>10.1f} {'+新增':>10}")
        elif b is None:
            lines.append(f"{k:<24} {a:>10.1f} {'—':>10} {'-消失':>10}")
        else:
            lines.append(f"{k:<24} {a:>10.1f} {b:>10.1f} {b - a:>+10.1f}")
    lines.append("-" * 60)
    lines.append(
        f"{'total':<24} {baseline.total_ms:>10.1f} {current.total_ms:>10.1f}"
        f" {current.total_ms - baseline.total_ms:>+10.1f}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.logging.analyze",
        description="启动耗时聚合与对比（读 logs/*.jsonl 的 cli.startup.total 事件）",
    )
    parser.add_argument("--dir", default="logs", help="日志目录（默认 logs/）")
    parser.add_argument("--last", type=int, default=None, help="只看最近 N 次")
    parser.add_argument(
        "--compare", type=int, nargs=2, metavar=("A", "B"),
        help="对比第 A 与第 B 次启动（按时间排序后的序号）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    events = load_events(args.dir)
    startups = collect_startups(events)

    if not startups:
        print(f"未在 {args.dir!r} 找到 {TOTAL_EVENT} 事件。")
        print("提示：.env 设置 DEEPDEV_LOG_FILE=logs/startup.jsonl 后，")
        print("每次启动会写一条 total 事件，多跑几次再对比。")
        return 1

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "idx": s.idx,
                        "ts": s.ts,
                        "workspace": s.workspace,
                        "total_ms": s.total_ms,
                        "phases": s.phases,
                        "source": s.source,
                    }
                    for s in startups
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(format_summary(startups, last=args.last))

    if args.compare:
        a, b = args.compare
        if a < 1 or b < 1 or a > len(startups) or b > len(startups):
            print(f"序号越界：共 {len(startups)} 次启动（1~{len(startups)}）")
            return 1
        print()
        print(format_compare(startups[a - 1], startups[b - 1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
