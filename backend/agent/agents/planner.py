"""Planner 子智能体定义。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from deepagents import SubAgent
from langchain_core.language_models import BaseChatModel

from backend.agent.prompts.planner import PLANNER_PROMPT


def build_planner_subagent(
    model: BaseChatModel | str,
    middleware: list[Any] | None = None,
    tools: Sequence[Any] | None = None,
) -> SubAgent:
    """
    构建 planner 子智能体配置。

    参数：
        model: 子智能体使用的模型。
        middleware: 附加 middleware 列表（如媒体净化中间件）。
            deepagents 的子智能体不会继承主 agent 的自定义 middleware，
            必须显式传入才会挂到子智能体自己的调用链上。
        tools: 显式工具集。传入后（含空列表）子智能体**不再继承主
            agent 的 MCP 工具**，避免每轮请求携带全量工具 schema
            的 token 开销。planner 只做只读规划，文件/执行能力由
            FilesystemMiddleware（backend 继承）提供，不依赖该参数。
            不传（None）则保持 deepagents 默认：继承主 agent 工具。

    返回：
        DeepAgents SubAgent 配置。
    """
    spec: SubAgent = {
        "name": "planner",
        "description": (
            "负责分析开发任务并制定简洁、可执行的执行计划。"
            "适用场景：需要多次运行迭代验证才能收口的任务（调参、运行时验证）、"
            "相互依赖的修改、较大重构、实施前需要先探查代码确定顺序的任务。"
            "只负责规划，不修改文件，不执行终端命令。"
        ),
        "model": model,
        "system_prompt": PLANNER_PROMPT,
    }
    if middleware:
        spec["middleware"] = list(middleware)
    if tools is not None:
        spec["tools"] = list(tools)
    return spec
