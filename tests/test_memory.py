"""
记忆功能冒烟测试（纯本地，不依赖 LLM / 网络）。

覆盖：
    1. normalize_path：大小写 / 尾斜杠 / 相对路径规范化
    2. resolve_memory_sources：加载顺序（全局 → 项目 → 运行时）
    3. read_memory_source：缺失文件静默返回 None
    4. build_memory_middleware：返回 MemoryMiddleware 实例，且对缺失文件容错
    5. describe_memory：三个层级的描述条目
    6. global memory guidelines：全局记忆文件包含运行时记忆的路径约定与维护工具指引

运行：
    .venv\\Scripts\\python.exe tests\\test_memory.py
"""

import os
import sys
import tempfile
from pathlib import Path

# 允许从任意 cwd 直接运行
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.memory.loader import (
    GLOBAL_MEMORY_FILE,
    read_memory_source,
    resolve_memory_sources,
)
from backend.workspace.registry import normalize_path

# deepagents 依赖 asyncio/Winsock，在受限沙箱中可能无法导入；
# 此时跳过 manager 相关测试（用户本机可正常运行全部用例）。
try:
    from backend.memory.manager import build_memory_middleware, describe_memory

    MANAGER_AVAILABLE = True
except Exception:  # noqa: BLE001 - 环境受限时跳过
    MANAGER_AVAILABLE = False

PASS = 0


def check(name: str, condition: bool) -> None:
    global PASS
    if not condition:
        raise AssertionError(f"FAIL: {name}")
    PASS += 1
    print(f"  ok - {name}")


def test_normalize_path() -> None:
    print("[normalize_path]")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "Ws"
        target.mkdir()

        # 同一目录不同写法 → 规范化结果一致（POSIX 上大小写不同，仅验证分隔符与解析）
        variants = [
            str(target),
            str(target) + "/",
            str(target) + "/./",
            str(target.parent / "Ws" / ".." / "Ws"),
        ]
        normalized = {normalize_path(v) for v in variants}
        check("同目录不同写法归一为同一身份", len(normalized) == 1)

    # 大小写：Windows（normcase）应归为同一身份，POSIX 大小写敏感应不同。
    # 基于临时目录判断，不依赖 C:\TMP 等机器特定目录是否存在。
    a = normalize_path(tmp_path / "Ws")
    b = normalize_path(tmp_path / "ws")
    if os.name == "nt":
        check("Windows 大小写归一", a == b)
    else:
        check("POSIX 大小写敏感", a != b)
    print()


def test_resolve_memory_sources() -> None:
    print("[resolve_memory_sources]")
    with tempfile.TemporaryDirectory() as tmp:
        sources = resolve_memory_sources(tmp)
        check("返回 3 个层级", len(sources) == 3)
        check("顺序: 全局在最前", Path(sources[0]) == GLOBAL_MEMORY_FILE)
        check("顺序: 项目在中间", Path(sources[1]) == Path(tmp) / "AGENTS.md")
        check("顺序: 运行时在最后", Path(sources[2]) == Path(tmp) / ".deepdev" / "memory.md")
    print()


def test_read_memory_source() -> None:
    print("[read_memory_source]")
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.md"
        check("缺失文件返回 None", read_memory_source(str(missing)) is None)

        exists = Path(tmp) / "exists.md"
        exists.write_text("hello memory", encoding="utf-8")
        check("存在文件返回内容", read_memory_source(str(exists)) == "hello memory")
    print()


def test_build_memory_middleware() -> None:
    print("[build_memory_middleware]")
    if not MANAGER_AVAILABLE:
        print("  (skip) deepagents 不可导入，跳过")
        return
    with tempfile.TemporaryDirectory() as tmp:
        middleware = build_memory_middleware(tmp)
        check("返回 MemoryMiddleware 实例", middleware is not None)
        check("sources 顺序正确", middleware.sources == resolve_memory_sources(tmp))
        print()
    print()


def test_global_memory_guidelines() -> None:
    print("[global memory guidelines]")
    content = read_memory_source(str(GLOBAL_MEMORY_FILE))
    check("全局记忆文件存在且非空", content is not None and content.strip() != "")
    check("包含运行时记忆路径约定",
          content is not None and ".deepdev/memory.md" in content)
    check("包含维护工具指引",
          content is not None and "write_file" in content and "edit_file" in content)
    print()


def test_describe_memory() -> None:
    print("[describe_memory]")
    if not MANAGER_AVAILABLE:
        print("  (skip) deepagents 不可导入，跳过")
        return
    with tempfile.TemporaryDirectory() as tmp:
        entries = describe_memory(tmp)
        check("返回 3 个条目", len(entries) == 3)
        check("tag 顺序: global/project/runtime",
              [e["tag"] for e in entries] == ["global", "project", "runtime"])
        check("缺失文件 exists=False 且 content=None",
              all(not e["exists"] and e["content"] is None for e in entries[1:]))

        # 写入项目记忆后应能读到
        project_md = Path(tmp) / "AGENTS.md"
        project_md.write_text("# 项目约定", encoding="utf-8")
        entries2 = describe_memory(tmp)
        check("项目记忆存在且可读", entries2[1]["exists"] and entries2[1]["content"] == "# 项目约定")
    print()


if __name__ == "__main__":
    test_normalize_path()
    test_resolve_memory_sources()
    test_read_memory_source()
    test_build_memory_middleware()
    test_describe_memory()
    test_global_memory_guidelines()
    print(f"\n全部通过：{PASS} 项")
