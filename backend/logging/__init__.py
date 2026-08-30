"""deepdev 本地日志：控制台人读 + 文件 JSONL 双路输出，零第三方依赖。

对外公共入口：

    setup_logging(level, log_file)   配置 deepdev.* logger
    StartupTimer                     启动阶段计时（with timer.phase(...) / timer.checkpoint(...)）
    log_event(name, **attrs)         发一条结构化事件
"""

from backend.logging.config import JsonlFormatter, setup_logging
from backend.logging.timers import Phase, StartupTimer, log_event

__all__ = [
    "JsonlFormatter",
    "Phase",
    "StartupTimer",
    "log_event",
    "setup_logging",
]
