"""
记忆组装层。

负责把 loader 解析出的记忆文件组装成 deepagents 的 MemoryMiddleware，
并向命令层暴露统一的查询接口。factory 与 CLI 只依赖本模块。

关键点：
    MemoryMiddleware 的 backend 必须使用独立的
    ``FilesystemBackend(virtual_mode=False)``，
    而不能复用 factory 中的 ``LocalShellBackend(virtual_mode=True)``：

    virtual_mode=True 会把所有路径当作工作区内的虚拟路径，
    工作区之外的文件（如全局记忆 backend/memory/global/AGENTS.md）
    会触发 INVALID_PATH 错误，导致加载失败。
"""

from __future__ import annotations

from typing import Any

from deepagents.backends import FilesystemBackend
from deepagents.middleware import MemoryMiddleware

from backend.memory import loader
from backend.workspace.manager import workspace_manager
from backend.workspace.registry import normalize_path

# 记忆层级的显示标签（与 resolve_memory_sources 顺序一一对应）
_MEMORY_TAGS = ("global", "project", "runtime")


def build_memory_middleware(workspace: str | None = None) -> Any | None:
    """构建记忆中间件。

    参数：
        workspace: 工作区路径；None 时回退到 workspace_manager 当前工作区。

    返回：
        MemoryMiddleware 实例；任何异常（含无工作区、backend 构造失败）
        返回 None —— 记忆故障绝不阻塞 agent 启动。
    """
    if workspace is None:
        try:
            workspace = workspace_manager.require_current()
        except RuntimeError:
            return None

    try:
        sources = loader.resolve_memory_sources(workspace)
        backend = FilesystemBackend(
            root_dir=normalize_path(workspace),
            virtual_mode=False,
        )
        return MemoryMiddleware(backend=backend, sources=sources)
    except Exception:
        return None


def describe_memory(workspace: str | None = None) -> list[dict]:
    """返回当前工作区记忆文件的描述列表，供命令层渲染。

    每项结构：
        {"tag": "global"|"project"|"runtime",
         "path": str,
         "exists": bool,
         "content": str | None}
    """
    if workspace is None:
        try:
            workspace = workspace_manager.require_current()
        except RuntimeError:
            return []

    result = []
    for tag, path in zip(_MEMORY_TAGS, loader.resolve_memory_sources(workspace)):
        content = loader.read_memory_source(path)
        result.append(
            {
                "tag": tag,
                "path": path,
                "exists": content is not None,
                "content": content,
            }
        )
    return result
