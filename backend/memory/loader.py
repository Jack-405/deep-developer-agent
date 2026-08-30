"""
记忆文件路径层。

职责：
    定义记忆文件的存放约定与路径解析，不 import 任何 deepagents 组件。

分层约定：
    global  —— 出厂通用约定，随 deepdev 源码分发（git 管理，随升级演进）
    project —— <workspace>/AGENTS.md，项目级约定，随项目仓库走（git 管理）
    runtime —— <workspace>/.deepdev/memory.md，deepdev 运行时记忆（.gitignore 隔离）

加载顺序固定为：全局 → 项目 → 运行时，后出现者覆盖先出现者
（由 MemoryMiddleware 的拼接语义保证「项目覆盖全局」）。
"""

from __future__ import annotations

from pathlib import Path

from backend.workspace.registry import normalize_path

# 锚定 deepdev 项目根：backend/memory/loader.py 向上两级
BASE_DIR = Path(__file__).resolve().parents[2]

# 全局出厂约定（git 管理，随 deepdev 升级）
GLOBAL_MEMORY_FILE = BASE_DIR / "backend" / "memory" / "global" / "AGENTS.md"

# 运行时记忆：工作区私有目录，由 .gitignore 统一隔离
RUNTIME_MEMORY_REL = Path(".deepdev") / "memory.md"


def resolve_memory_sources(workspace: str | Path) -> list[str]:
    """返回按加载顺序排列的记忆文件绝对路径列表。

    - 顺序固定：全局 → 项目(workspace/AGENTS.md) → 运行时(.deepdev/memory.md)
    - global 为出厂常量（由 ``__file__.resolve()`` 推导，天然绝对规范路径，
      保留原大小写便于终端展示）；project / runtime 由 workspace 派生，
      经 ``normalize_path`` 规范化，同一工作区不同写法得到相同结果
    - 不在此处过滤缺失文件：缺失由 MemoryMiddleware 静默跳过（FILE_NOT_FOUND），
      与命令层 ``read_memory_source`` 返回 None 的语义一致
    """
    ws = Path(normalize_path(workspace))
    return [
        str(GLOBAL_MEMORY_FILE),
        str(ws / "AGENTS.md"),
        str(ws / RUNTIME_MEMORY_REL),
    ]


def read_memory_source(path: str) -> str | None:
    """读取记忆文件内容；不存在或不可读时返回 None（静默跳过）。"""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None
