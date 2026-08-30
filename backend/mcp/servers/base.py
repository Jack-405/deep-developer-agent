"""MCP server 抽象：MCPServerSpec 与 LaunchSpec。

设计意图：

- 一个 MCP server（如 godot-ai、obsidian-mcp、任意 DEEPDEV_MCP_EXTRA
  声明的 server）在 deepdev 中表现为一个 ``MCPServerSpec`` —— 静态声明
  + 纯函数，注册进 ``registry.build_registry()``。
- 不管 server 长什么样，最终都收敛成 ``LaunchSpec``（一条启动命令：
  command + args + env），由 MCPManager 按传输方式拉起。
- server 自身不碰 langchain / mcp SDK；与外部进程交互的所有细节都收敛
  在 manager（client.py）一侧。

一期只支持 ``transport="stdio"``（与 godot 现状一致）。
HTTP / Streamable HTTP 传输是未来扩展点（字段已预留，分派逻辑留 TODO）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Transport = Literal["stdio", "streamable_http"]
Scope = Literal["workspace", "global"]


@dataclass(frozen=True)
class LaunchSpec:
    """一个 MCP server 的启动规格（所有 server 的统一收敛点）。"""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    # streamable_http 传输时使用（一期不实现，预留字段）
    url: str | None = None
    health_url: str | None = None


class MCPServerSpec(Protocol):
    """MCP server 的静态声明（实现方：godot/spec.py、obsidian/spec.py）。

    各方法约定：

    - ``enabled()``：总开关（读 settings 对应 `*_ENABLED` 配置）。
    - ``ready()``：依赖就绪（二进制/源码目录存在）。返回 False 时该
      server 整体跳过，不影响其它 server 与 agent 启动。
    - ``applicable(workspace)``：workspace 维度判定。workspace 作用域的
      server 在此探测项目特征（如 Godot 的 project.godot）；global 作用域
      的 server 恒返回 True（是否启用由 enabled + ready 决定）。
    - ``build_launch()``：构造启动命令。
    - ``build_prompt()``：加载后注入主提示词的引导文本；返回 None 表示
      该 server 无引导（当前仅 godot/obsidian 两类都有引导）。
    """

    name: str
    scope: Scope
    transport: Transport

    def enabled(self) -> bool: ...

    def ready(self) -> bool: ...

    def applicable(self, workspace: str) -> bool: ...

    def build_launch(self) -> LaunchSpec: ...

    def build_prompt(self) -> str | None: ...
