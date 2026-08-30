"""媒体内容净化中间件。

背景
----
deepagents 的 read_file 工具对非文本文件（图片/音频/视频/PDF）不返回文本，
而是返回多模态内容块：``content_blocks=[{"type": "image", "base64": ..., "mime_type": ...}]``
（见 deepagents/middleware/filesystem.py 的 _handle_read_result）。

序列化到 OpenAI 兼容 API 时，langchain 会把这类块转成 ``image_url``
（``data:image/png;base64,...``）。若配置的模型端点是纯文本模型（不支持视觉），
服务端反序列化会直接 400 拒绝：``unknown variant 'image_url', expected 'text'``，
导致整个流式会话崩溃——这正是"读图片看效果"时经常遇到的报错。

另外，大图整张 base64 塞进请求体会让 payload 膨胀到 MB 级，即便端点支持视觉
也是极大的 token 浪费。

方案
----
在模型调用前（middleware 栈最内层）把所有消息中的非文本内容块替换为文本占位，
保证发往模型端的请求永远只有 text 块。主 agent 与子代理（planner/test）共用
同一条 model 调用链，因此该中间件对两者同时生效。

实现说明
--------
- ``sanitize_media_blocks`` / ``_sanitize_message`` 是纯函数（零第三方依赖），
  可独立单测。
- deepagents/langchain 的导入放在 build_* 函数内部延迟执行，构造失败返回 None，
  媒体净化故障绝不阻塞 agent 启动（与 memory/skills 的容错约定一致）。
"""

from __future__ import annotations

from typing import Any

# 消息 content 中非文本块的占位文案（尽量带上被读文件的虚拟路径）
_MEDIA_PLACEHOLDER = (
    "[图片/音频/视频等多媒体内容已省略：当前模型不支持多模态输入，"
    "无法查看图片或收听音频。若确需图片信息，可改用 execute 读取图片元数据"
    "（尺寸、格式等）代替。]"
)


def _is_text_block(block: Any) -> bool:
    """判定 content 块是否为文本块（字符串或 type == "text" 的 dict）。"""
    if isinstance(block, str):
        return True
    return isinstance(block, dict) and block.get("type") == "text"


def sanitize_media_blocks(content: Any, read_file_path: str | None = None) -> Any:
    """把消息 content 中的非文本块替换为文本占位。

    参数：
        content: 消息的 content（可能是 str 或内容块 list）。
        read_file_path: 可选，被读文件的路径（来自 additional_kwargs），
            会拼进占位文案方便模型理解。

    返回：
        替换后的 content。若无非文本块或 content 不是 list，原样返回。
    """
    if not isinstance(content, list):
        return content

    text_blocks = [b for b in content if _is_text_block(b)]
    media_blocks = [b for b in content if not _is_text_block(b)]
    if not media_blocks:
        return content

    if read_file_path:
        placeholder = (
            f"[多媒体内容已省略：{read_file_path}（当前模型不支持多模态输入，"
            "无法查看图片/音频/视频）]"
        )
    else:
        placeholder = _MEDIA_PLACEHOLDER

    new_content: list[Any] = list(text_blocks)
    new_content.append({"type": "text", "text": placeholder})
    return new_content


def _sanitize_message(message: Any) -> Any:
    """净化单条消息：剥离非文本内容块，返回新的消息对象。

    仅处理 content 为 list 的消息（多模态内容块只会出现在这种情况下）。
    使用 ``model_copy`` 生成新消息，不修改原消息。
    """
    content = message.content
    if not isinstance(content, list):
        return message

    read_file_path = None
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        read_file_path = additional_kwargs.get("read_file_path")

    new_content = sanitize_media_blocks(content, read_file_path)
    if new_content is content:
        return message
    return message.model_copy(update={"content": new_content})


def build_media_sanitizer_middleware() -> Any | None:
    """构建媒体净化中间件。

    返回：
        AgentMiddleware 实例；langchain 不可导入等异常返回 None。
    """
    try:
        from langchain.agents.middleware.types import AgentMiddleware

        class _NoMediaMiddleware(AgentMiddleware[Any, Any, Any]):
            """把请求消息中的多模态内容块替换为文本占位。"""

            def wrap_model_call(
                self,
                request: Any,
                handler: Any,
            ) -> Any:
                sanitized = [_sanitize_message(m) for m in request.messages]
                return handler(request.override(messages=sanitized))

            async def awrap_model_call(
                self,
                request: Any,
                handler: Any,
            ) -> Any:
                sanitized = [_sanitize_message(m) for m in request.messages]
                return await handler(request.override(messages=sanitized))

        return _NoMediaMiddleware()
    except Exception:  # noqa: BLE001 - 构造失败绝不阻塞 agent 启动
        return None
