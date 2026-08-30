"""MCP 工具名冲突检测与改名规划（纯函数，零第三方依赖）。

多 MCP server 聚合后，不同 server 可能暴露同名工具（如 godot 与
obsidian 都可能有 read/search 之类）。同名工具在 create_deep_agent
的 tools= 列表里会互相覆盖或导致调用歧义。

策略：按 registry 顺序，**先加载的 server 保留原名**，后加载的
server 的冲突工具改名为 ``<server>_<原名>``。这样 godot prompt 中
硬编码的工具名永远有效，新接入方（obsidian）按需加前缀。

注意：改名只发生在**确实撞名**时；无冲突则所有工具保持原名，模型
看到的名字与 MCP server 暴露的一致，语义最清晰。
"""

from __future__ import annotations

from typing import Mapping, Sequence


def plan_conflict_renames(
    per_server_names: Mapping[str, Sequence[str]],
) -> dict[str, dict[str, str]]:
    """规划冲突改名。

    参数：
        per_server_names: server → 工具名列表，**顺序即优先级**（先出现的
            server 保留原名）。

    返回：
        server → {原名: 新名}。无冲突的 server 不出现在返回 dict 中。
        新名格式为 ``f"{server}_{name}"``。
    """
    renames: dict[str, dict[str, str]] = {}
    seen: set[str] = set()

    for server, names in per_server_names.items():
        server_renames: dict[str, str] = {}
        for name in names:
            if name in seen:
                server_renames[name] = f"{server}_{name}"
            else:
                seen.add(name)
        if server_renames:
            renames[server] = server_renames

    return renames
