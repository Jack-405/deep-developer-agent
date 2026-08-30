"""
Media Sanitizer 单测（纯本地，不依赖 LLM / deepagents / langchain）。

覆盖：
    1. sanitize_media_blocks：纯文本 list 原样返回（同一对象）
    2. 非 list content（纯字符串）原样返回
    3. 图片 content block（type=image + base64）→ 替换为文本占位
    4. 文本 + 图片混合 → 保留文本、追加占位
    5. read_file_path 会拼进占位文案
    6. _sanitize_message：多模态 ToolMessage 被净化，且不修改原消息
    7. 无多模态内容的消息原样返回
    8. build_media_sanitizer_middleware：返回中间件实例（langchain 不可用时跳过）

运行：
    .venv\\Scripts\\python.exe tests\\test_media_sanitizer.py
"""

import copy
import sys
from pathlib import Path

# 允许从任意 cwd 直接运行: python tests/test_media_sanitizer.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.agent.middleware.media_sanitizer import (  # noqa: E402  (import after sys.path fix)
    _sanitize_message,
    build_media_sanitizer_middleware,
    sanitize_media_blocks,
)

PASS = 0


def check(name: str, condition: bool) -> None:
    global PASS
    if not condition:
        raise AssertionError(f"FAIL: {name}")
    PASS += 1
    print(f"  ok - {name}")


class _FakeMessage:
    """最小消息替身：只暴露 media_sanitizer 用到的字段，避免依赖 langchain_core。"""

    def __init__(self, content, additional_kwargs=None):
        self.content = content
        self.additional_kwargs = additional_kwargs or {}

    def model_copy(self, update=None):
        new = copy.copy(self)
        for key, value in (update or {}).items():
            setattr(new, key, value)
        return new


def _img_block(mime="image/png"):
    return {"type": "image", "base64": "aGVsbG8=", "mime_type": mime}


def test_pure_text_list_unchanged():
    content = [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]
    check("纯文本 list 原样返回", sanitize_media_blocks(content) is content)


def test_non_list_content_unchanged():
    content = "just a string"
    check("字符串 content 原样返回", sanitize_media_blocks(content) is content)


def test_image_block_replaced():
    content = [_img_block()]
    result = sanitize_media_blocks(content)
    check("图片块被替换为文本占位", isinstance(result, list) and len(result) == 1)
    check("占位是 text 块", isinstance(result[0], dict) and result[0]["type"] == "text")
    check("占位文案包含提示", "多模态" in result[0]["text"] or "多媒体" in result[0]["text"])
    check("原 content 未被修改", content == [_img_block()])


def test_mixed_text_and_image():
    content = [{"type": "text", "text": "keep me"}, _img_block()]
    result = sanitize_media_blocks(content)
    check("混合时保留文本块", any(b.get("text") == "keep me" for b in result if isinstance(b, dict)))
    check("混合时追加占位", any(isinstance(b, dict) and b["type"] == "text" and "省略" in b.get("text", "") for b in result))
    check("混合时无图片块残留", all(not (isinstance(b, dict) and b["type"] != "text") for b in result))


def test_read_file_path_in_placeholder():
    content = [_img_block()]
    result = sanitize_media_blocks(content, read_file_path="/resource/horse.png")
    check("read_file_path 拼进占位", any("/resource/horse.png" in b.get("text", "") for b in result if isinstance(b, dict)))


def test_sanitize_message_tool_message():
    msg = _FakeMessage(
        [_img_block()],
        additional_kwargs={"read_file_path": "/resource/iron.png", "read_file_media_type": "image/png"},
    )
    new = _sanitize_message(msg)
    check("多模态消息被替换", new is not msg)
    check("净化后是文本块", isinstance(new.content, list) and all(isinstance(b, dict) and b["type"] == "text" for b in new.content))
    check("占位含文件路径", any("/resource/iron.png" in b.get("text", "") for b in new.content if isinstance(b, dict)))
    check("原消息未被修改", msg.content == [_img_block()])


def test_sanitize_message_noop():
    msg = _FakeMessage([{"type": "text", "text": "plain"}])
    check("无多模态内容原样返回", _sanitize_message(msg) is msg)


def test_build_middleware():
    middleware = build_media_sanitizer_middleware()
    if middleware is None:
        print("  skip - build_media_sanitizer_middleware 返回 None（langchain 不可导入）")
        return
    check("build_media_sanitizer_middleware 返回中间件", middleware is not None)


if __name__ == "__main__":
    test_pure_text_list_unchanged()
    test_non_list_content_unchanged()
    test_image_block_replaced()
    test_mixed_text_and_image()
    test_read_file_path_in_placeholder()
    test_sanitize_message_tool_message()
    test_sanitize_message_noop()
    test_build_middleware()
    print(f"\nmedia_sanitizer: {PASS} checks passed")
