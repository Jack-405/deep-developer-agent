"""
MCP 工具名冲突检测与改名规划（纯函数，无第三方依赖）。

覆盖：
    1. 无冲突 → 不改名（返回空 dict）
    2. 跨 server 同名 → 只改后加载方（先加载方保名）
    3. 新名前缀格式 server_name
    4. 多个冲突、多个 server 混合场景
    5. 顺序即优先级：交换顺序后改名方互换

运行：
    .venv\\Scripts\\python.exe tests\\test_mcp_conflicts.py
"""

import sys
from pathlib import Path

# 允许从任意 cwd 直接运行
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.mcp.conflicts import plan_conflict_renames  # noqa: E402

_PASS = 0
_FAIL = 0


def check(label: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"[PASS] {label}")
    else:
        _FAIL += 1
        print(f"[FAIL] {label}")


def test_no_conflict() -> None:
    result = plan_conflict_renames({
        "godot": ["session_activate", "scene_get_hierarchy"],
        "obsidian": ["note_read", "search_text"],
    })
    check("无冲突返回空 dict", result == {})


def test_cross_server_conflict() -> None:
    result = plan_conflict_renames({
        "godot": ["read_file", "write_file"],
        "obsidian": ["read_file", "search_text"],
    })
    check("先加载方保名", "godot" not in result)
    check("后加载方改名", result.get("obsidian") == {"read_file": "obsidian_read_file"})


def test_prefix_format() -> None:
    result = plan_conflict_renames({
        "a": ["x"],
        "b": ["x"],
    })
    check("前缀为 server_name", result["b"]["x"] == "b_x")


def test_multiple_conflicts() -> None:
    result = plan_conflict_renames({
        "godot": ["search", "open"],
        "obsidian": ["search", "read"],
        "other": ["read", "search"],
    })
    check("obsidian.search 改名", result["obsidian"]["search"] == "obsidian_search")
    check("other.read 改名", result["other"]["read"] == "other_read")
    check("other.search 改名", result["other"]["search"] == "other_search")


def test_order_is_priority() -> None:
    result = plan_conflict_renames({
        "obsidian": ["note_read"],
        "godot": ["note_read"],
    })
    check("顺序交换后 godot 被改名", result.get("godot") == {"note_read": "godot_note_read"})
    check("obsidian 保名", "obsidian" not in result)


if __name__ == "__main__":
    test_no_conflict()
    test_cross_server_conflict()
    test_prefix_format()
    test_multiple_conflicts()
    test_order_is_priority()

    print()
    if _FAIL:
        print(f"test_mcp_conflicts: {_FAIL} FAILED, {_PASS} passed")
        sys.exit(1)
    print(f"test_mcp_conflicts: ALL PASS ({_PASS})")
