"""
DeepAgents Stream Adapter

负责：

1. 消费 DeepAgents / LangGraph stream
2. 解析不同 stream_mode
3. 转换成 CLI 可消费、经过去重与精简的事件

事件类型：

- text        模型输出文本（流式 token）
- status      agent 思考状态（每轮只发一次）
- tool_start  工具调用开始（每个工具调用只发一次，携带单行展示摘要）
- tool_end    工具调用结束（携带 success / error 状态）
- custom      自定义事件
- error       流式执行错误
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Iterator

from langchain_core.messages import AIMessageChunk, ToolMessage

logger = logging.getLogger(__name__)


class StreamEventType:
    TEXT = "text"
    STATUS = "status"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    CUSTOM = "custom"
    ERROR = "error"






async def stream_agent(
    agent: Any,
    messages: list[dict[str, str]],
    thread_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    DeepAgents 流式执行入口。

    agent.astream() 返回 AsyncIterator。
    每轮调用只产生一次"正在思考"状态。

    thread_id:
        会话标识。透传给 LangGraph config（configurable.thread_id），
        SummarizationMiddleware 据此把对话历史落盘到
        conversation_history/{thread_id}.md。
        不传时 deepagents 会生成随机的 session_xxxxxx。
    """
    thinking_emitted = False

    config = (
        {"configurable": {"thread_id": thread_id}}
        if thread_id
        else None
    )

    try:

        async for chunk in agent.astream(
            {"messages": messages},
            config=config,
            stream_mode=["messages", "updates", "custom"],
            version="v2",
        ):
            chunk_type = chunk.get("type")

            if chunk_type == "messages":
                for event in handle_message(chunk):
                    yield event

            elif chunk_type == "updates":
                for event in handle_update(chunk):
                    if event["type"] == StreamEventType.STATUS and thinking_emitted:
                        continue
                    if event["type"] == StreamEventType.STATUS:
                        thinking_emitted = True
                    yield event

            elif chunk_type == "custom":
                yield {
                    "type": StreamEventType.CUSTOM,
                    "data": chunk.get("data"),
                }

    except Exception as e:
        logger.exception("DeepAgents streaming failed")
        yield {
            "type": StreamEventType.ERROR,
            "data": str(e),
        }


def handle_message(
    chunk: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """
    解析 messages stream（stream_mode="messages"）。

    只保留模型输出的文本 token；工具调用相关事件统一由
    handle_update 基于 updates stream 产生，避免分片重复与噪声。
    """
    token, metadata = chunk["data"]

    if isinstance(token, AIMessageChunk) and token.content:
        yield {
            "type": StreamEventType.TEXT,
            "data": token.content,
            "metadata": metadata,
        }


def handle_update(
    chunk: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """
    解析 updates stream（stream_mode="updates"）。

    节点：
    - model：模型响应，包含完整的 tool_calls -> 产生 tool_start
    - tools：工具执行结果（ToolMessage）-> 产生 tool_end

    注意：langchain create_agent 图中不存在 "model_request" 节点，
    "正在思考" 状态由 stream_agent 基于首个 model 调用去重产生。
    """
    data = chunk.get("data", {}) or {}

    for node_name, value in data.items():
        if node_name == "model":
            # langchain create_agent 图中不存在 "model_request" 节点；
            # "正在思考" 状态挂在 model 节点上，由 stream_agent 去重为每轮一次。
            yield {
                "type": StreamEventType.STATUS,
                "data": "正在思考…",
            }

            for message in (value or {}).get("messages", []):
                tool_calls = getattr(message, "tool_calls", None)
                if not tool_calls:
                    continue
                for call in tool_calls:
                    name = str(call.get("name", "unknown"))
                    args = call.get("args") or {}
                    yield {
                        "type": StreamEventType.TOOL_START,
                        "data": {
                            "name": name,
                            "summary": _summarize_args(name, args),
                            "args": args,
                        },
                    }

        elif node_name == "tools":
            for message in (value or {}).get("messages", []):
                if not isinstance(message, ToolMessage):
                    continue
                yield {
                    "type": StreamEventType.TOOL_END,
                    "data": {
                        "name": getattr(message, "name", "unknown"),
                        "status": getattr(message, "status", None) or "success",
                    },
                }


MAX_SUMMARY_LEN = 120


def _summarize_args(name: str, args: dict[str, Any] | None) -> str:
    """把工具参数压缩成适合终端单行展示的摘要。

    短字段（路径/模式/命令）直接展示；大文本字段只报长度；
    结构化列表（如 todos）只报条目数。
    """
    if not args:
        return name

    parts: list[str] = []

    for key in ("file_path", "path", "pattern", "glob", "command"):
        value = args.get(key)
        if value in (None, ""):
            continue
        text = str(value).replace("\n", " ")
        if len(text) > 40:
            text = text[:37] + "..."
        parts.append(f"{key}={text}")

    for key in ("content", "new_string", "old_string"):
        value = args.get(key)
        if value in (None, ""):
            continue
        parts.append(f"{key}=<{len(str(value))} chars>")

    for key in ("todos",):
        value = args.get(key)
        if isinstance(value, list):
            parts.append(f"{key}=<{len(value)} items>")

    if not parts:
        return name

    summary = f"{name} " + " ".join(parts)
    if len(summary) > MAX_SUMMARY_LEN:
        summary = summary[: MAX_SUMMARY_LEN - 3] + "..."
    return summary