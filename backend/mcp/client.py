"""通用 MCP 客户端。

接入形态：MCP server 是**黑盒进程**（godot-ai、obsidian-mcp 等），
本项目只经 MCP 协议与其交互，绝不 import 其内部代码。

启动链路（stdio，一期只支持此传输）：

    <LaunchSpec.command> <LaunchSpec.args...>
        └─ MCP stdio 子进程，工具经 JSON-RPC 暴露

工具加载：mcp SDK 的 stdio_client 拉起子进程 → ClientSession.initialize()
→ langchain-mcp-adapters 把工具声明转成 BaseTool，交给
create_deep_agent(tools=...)。

生命周期：

- MCPManager 是 **REPL 级单例**（cli/main.py 启动后负责 shutdown）。
- 会话缓存键：
    - workspace 作用域 server（godot）：``(name, workspace)`` —— 每个
      工作区一个会话，切工作区不重启同区会话。
    - global 作用域 server（obsidian）：``(name, "_global_")`` —— 与
      workspace 无关，app 启动即加载。
- 工具加载失败返回空列表，**不阻断 agent 启动**；会话随后被释放，
  下次 collect 时重新拉起。
- 工具名冲突：不同 server 暴露同名工具时，按 registry 顺序，后加载
  方改名为 ``<server>_<原名>``（见 conflicts.py）。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from contextlib import AsyncExitStack
from typing import Any

# mcp / langchain-mcp-adapters 是运行时可选依赖：
# 未安装（如未执行 uv sync）时降级为无 MCP 工具，不阻断 CLI 启动。
try:
    from langchain_mcp_adapters.tools import load_mcp_tools
    from mcp import ClientSession, StdioServerParameters, stdio_client
    _MCP_IMPORT_OK = True
except ImportError:  # pragma: no cover - 依赖缺失时的降级路径
    _MCP_IMPORT_OK = False

from backend.logging import StartupTimer
from backend.mcp.conflicts import plan_conflict_renames
from backend.mcp.registry import build_registry
from backend.mcp.servers.base import LaunchSpec, MCPServerSpec

logger = logging.getLogger(__name__)

_GLOBAL_KEY = "_global_"


class MCPSession:
    """单个 MCP server 会话（子进程 + MCP 会话 + 工具缓存）。"""

    def __init__(self, server_name: str, launch: LaunchSpec) -> None:
        self.server_name = server_name
        self._launch = launch
        self._stack = AsyncExitStack()
        self._tools: list | None = None

    async def start(self) -> None:
        """拉起 MCP 子进程并加载工具。"""
        if not _MCP_IMPORT_OK:
            raise RuntimeError(
                "MCP 依赖未安装（mcp / langchain-mcp-adapters），"
                "请先执行 `uv sync` 后再启用 MCP 集成。"
            )
        server_params = StdioServerParameters(
            command=self._launch.command,
            args=self._launch.args,
            env=self._launch.env or {**os.environ},
        )

        read, write = await self._stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await session.initialize()
        self._tools = await load_mcp_tools(session)

    async def get_tools(self) -> list:
        """返回 MCP 工具列表（懒启动）。"""
        if self._tools is None:
            await self.start()
        return list(self._tools or [])

    async def close(self) -> None:
        """关闭子进程与会话（幂等）。"""
        try:
            await self._stack.aclose()
        finally:
            self._tools = None


class MCPManager:
    """REPL 级单例：按 registry 遍历所有 MCP server，按作用域缓存会话。"""

    def __init__(
        self, registry: Sequence[MCPServerSpec] | None = None
    ) -> None:
        # 默认走 build_registry()：内置适配器 + DEEPDEV_MCP_EXTRA 通用项。
        # 显式传入 registry 用于测试注入。
        self._registry = tuple(registry) if registry is not None else build_registry()
        self._sessions: dict[tuple[str, str], MCPSession] = {}

    # ------------------------------------------------------------------
    # 会话缓存
    # ------------------------------------------------------------------

    def _session_key(self, spec: MCPServerSpec, workspace: str) -> tuple[str, str]:
        if spec.scope == "global":
            return (spec.name, _GLOBAL_KEY)
        return (spec.name, workspace)

    async def _close_session(self, key: tuple[str, str]) -> None:
        session = self._sessions.pop(key, None)
        if session is not None:
            await session.close()

    # ------------------------------------------------------------------
    # 工具聚合
    # ------------------------------------------------------------------

    async def collect(self, workspace: str) -> tuple[list[MCPServerSpec], list[Any]]:
        """聚合当前 workspace 下所有适用 MCP server 的工具。

        多个 server **串行启动**（判定→拉起→加载，逐个进行），不用
        asyncio.gather 并发：mcp SDK 的 stdio_client / ClientSession
        内部用 anyio 任务组（cancel scope），上下文必须"进入与退出在同一
        task"；并发拉起后 REPL 退出时主 task 关闭会话会抛 RuntimeError:
        Attempted to exit cancel scope in a different task（2026-08 回归）。

        返回 ``(loaded_specs, tools)``：

        - ``loaded_specs``：实际加载成功的 server（用于驱动 prompt sections）。
        - ``tools``：聚合后的 BaseTool 列表；已就地处理工具名冲突
          （后加载方加 ``<server>_`` 前缀）。

        单个 server 的任何失败（判定/启动/加载）都只记日志并跳过该
        server，不阻断整体与 agent 启动。
        """
        loaded_specs: list[MCPServerSpec] = []
        collected: list[tuple[str, Any]] = []  # (server_name, tool)
        candidates: list[MCPServerSpec] = []

        # 启动量化：每个 server 的拉起（start）与工具加载（tools）单独计时，
        # 事件带 server 属性，控制台人读、JSONL 文件可聚合对比。
        timer = StartupTimer()

        for spec in self._registry:
            try:
                if not (spec.enabled() and spec.ready() and spec.applicable(workspace)):
                    continue
            except Exception:
                logger.exception("判定 MCP server %s 可用性失败，跳过", spec.name)
                continue

            if spec.transport != "stdio":
                logger.warning(
                    "MCP server %s 传输 %s 暂不支持（一期仅 stdio），跳过",
                    spec.name,
                    spec.transport,
                )
                continue
            candidates.append(spec)

        # 串行启动：判定（enabled/ready/applicable）是同步快操作；start()
        # （拉子进程 + initialize + 加载工具）逐个进行。曾用 asyncio.gather
        # 并发拉起（每个协程一个 task），但 mcp 的 stdio_client /
        # ClientSession 内部用 anyio 任务组，上下文必须"进入与退出同一
        # task"——并发版本在 REPL 退出 shutdown 时（主 task 关闭 gather
        # task 里进入的上下文）抛 RuntimeError: Attempted to exit cancel
        # scope in a different task。串行让 enter/exit 都在主 task，规避。
        async def _load_one(
            spec: MCPServerSpec,
        ) -> tuple[MCPServerSpec, list[Any]] | None:
            """启动（或复用缓存）单个 server 并取回工具；失败返回 None。"""
            key = self._session_key(spec, workspace)
            session = self._sessions.get(key)
            if session is None:
                try:
                    with timer.phase("mcp.start", server=spec.name):
                        session = MCPSession(spec.name, spec.build_launch())
                        await session.start()
                except Exception:
                    logger.exception("启动 MCP server %s 会话失败", spec.name)
                    if session is not None:
                        try:
                            await session.close()
                        except Exception:
                            logger.exception(
                                "关闭 MCP server %s 失败会话时出错", spec.name
                            )
                    return None
                self._sessions[key] = session

            try:
                with timer.phase("mcp.tools", server=spec.name):
                    tools = await session.get_tools()
            except Exception:
                logger.exception("加载 MCP server %s 工具失败", spec.name)
                try:
                    await self._close_session(key)
                except Exception:
                    logger.exception("关闭 MCP server %s 会话时出错", spec.name)
                return None
            return spec, tools

        # 串行 await（见上：并发会让 anyio 上下文跨 task 关闭而崩溃）。
        for spec in candidates:
            result = await _load_one(spec)
            if result is None:
                continue
            spec, tools = result
            loaded_specs.append(spec)
            for tool in tools:
                collected.append((spec.name, tool))

        # 工具名冲突处理：按 server 分组（顺序即优先级），后加载方改名。
        per_server_names: dict[str, list[str]] = {}
        for server_name, tool in collected:
            per_server_names.setdefault(server_name, []).append(tool.name)

        renames = plan_conflict_renames(per_server_names)
        for server_name, tool in collected:
            rename_map = renames.get(server_name)
            if rename_map and tool.name in rename_map:
                new_name = rename_map[tool.name]
                logger.warning(
                    "MCP 工具名冲突：%s 的工具 %s 改名为 %s",
                    server_name,
                    tool.name,
                    new_name,
                )
                # BaseTool.name 是可赋值的 pydantic 字段；改名只影响模型
                # 看到的 schema 名，远端 MCP 调用名在 load_mcp_tools 构造
                # 时已闭包捕获，不受影响。
                tool.name = new_name

        timer.summary(
            name="mcp.collect.total",
            workspace=workspace,
            loaded=[s.name for s in loaded_specs],
        )
        return loaded_specs, [tool for _, tool in collected]

    # ------------------------------------------------------------------
    # 回收
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """REPL 退出时统一回收所有会话（幂等）。"""
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()


# REPL 级单例：进程存活期间复用，不随 agent 重建
mcp_manager = MCPManager()
