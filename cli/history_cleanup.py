"""
conversation_history 保留策略。

deepagents 的 SummarizationMiddleware 会把压缩裁掉的消息落盘到
<workspace>/.deepdev/conversation_history/{thread_id}.md（只增不减）。

本模块负责按保留策略自动清理旧文件：默认仅保留最近 10 个会话历史文件，
更早的归档在 CLI 启动时删除。

注意：
    清理的是会话历史归档（conversation_history）。
    运行时记忆 <workspace>/.deepdev/memory.md 由模型按记忆指引维护，
    不在此清理范围内。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_KEEP = 10


def conversation_history_dir(workspace: str) -> Path:
    """返回会话历史目录（<workspace>/.deepdev/conversation_history）。"""
    return Path(workspace) / ".deepdev" / "conversation_history"


def cleanup_conversation_history(
    workspace: str,
    keep: int = DEFAULT_KEEP,
) -> int:
    """清理旧的会话历史文件，仅保留最近 `keep` 个。

    按文件修改时间从新到旧排序，删除第 keep+1 个及更旧的文件。

    参数：
        workspace: 工作区目录路径。
        keep: 保留的历史文件数量。

    返回：
        删除的文件数量。
        目录不存在或没有文件时安全返回 0。
    """

    history_dir = conversation_history_dir(workspace)

    if not history_dir.is_dir():
        return 0

    files = sorted(
        history_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    removed = 0

    for stale in files[keep:]:

        try:

            stale.unlink()
            removed += 1

        except OSError:

            logger.warning(
                "Failed to remove stale history file: %s",
                stale,
            )

    if removed:

        logger.info(
            "Removed %d stale conversation history file(s), kept %d.",
            removed,
            keep,
        )

    return removed
