"""主 Agent（developer）系统提示词。

提示词按 section 分层组装：

    base → subagents → mcp（→ 各 MCP server 引导）

后续新增 MCP 时：

1. 在 prompts/sections/ 下新建模块，定义该 MCP 的使用引导。
2. 在对应 server 的 spec.build_prompt() 中返回该引导文本。

这样主提示词保持与具体集成解耦，新增能力不需要改动 base/subagents。
"""

from backend.agent.prompts.base import BASE_PROMPT
from backend.agent.prompts.sections.mcp import MCP_PROMPT
from backend.agent.prompts.sections.subagents import SUBAGENTS_PROMPT


def build_system_prompt(*, mcp_sections: list[str] | tuple[str, ...] = ()) -> str:
    """
    按运行环境组装主 Agent 系统提示词。

    参数：
        mcp_sections:
            实际加载的 MCP server 引导文本列表（由 factory 传入，
            来自各 server spec.build_prompt()）。未加载任何 MCP 时为空。

    返回：
        组合后的系统提示词字符串。
    """
    sections = [BASE_PROMPT, SUBAGENTS_PROMPT, MCP_PROMPT]
    sections.extend(mcp_sections)
    return "\n\n".join(s for s in sections if s and s.strip())


# 向后兼容：不含任何 MCP 引导的基础提示词。
SYSTEM_PROMPT = build_system_prompt()
