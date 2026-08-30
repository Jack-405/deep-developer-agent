from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录：backend/config/settings.py 向上两级
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    MODEL_NAME: str = ""
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""

    # ------------------------------------------------------------------
    # Godot MCP 集成（deepdev → godot-ai attach）
    #
    # 机器相关配置全部走环境变量 / .env，项目文件不写绝对路径：
    #   DEEPDEV_GODOT_ENABLED    是否启用（默认 true，写 false 可关）
    #   DEEPDEV_GODOT_AI_DIR     godot-ai 源码目录（空 = 约定相对路径 vendor/godot-ai）
    #   DEEPDEV_GODOT_PROJECT_PATH Godot 项目路径（空 = 自动探测 workspace 下的 project.godot）
    #   DEEPDEV_GODOT_PORT       共享后端 HTTP 端口（godot-ai attach --port）
    #   DEEPDEV_GODOT_WS_PORT    Godot 插件 WebSocket 端口（godot-ai attach --ws-port）
    # ------------------------------------------------------------------
    DEEPDEV_GODOT_ENABLED: bool = True
    DEEPDEV_GODOT_AI_DIR: str = ""
    DEEPDEV_GODOT_PROJECT_PATH: str = ""
    DEEPDEV_GODOT_PORT: int = 8000
    DEEPDEV_GODOT_WS_PORT: int = 9500

    # ------------------------------------------------------------------
    # Obsidian MCP 集成（deepdev → obsidian-mcp）
    #
    # 机器相关配置全部走环境变量 / .env，项目文件不写绝对路径：
    #   OBSIDIAN_ENABLED    是否启用（默认 true，写 false 可关）
    #   OBSIDIAN_BIN        obsidian-mcp 可执行文件完整路径（空 = 自动探测 PATH/常见安装位置）
    #   OBSIDIAN_VAULT_PATH Obsidian vault 目录（必填；v1 不做自动探测）
    # ------------------------------------------------------------------
    OBSIDIAN_ENABLED: bool = True
    OBSIDIAN_BIN: str = ""
    OBSIDIAN_VAULT_PATH: str = ""

    # ------------------------------------------------------------------
    # 通用 MCP 接入（配置驱动，无需改代码）
    #
    #   DEEPDEV_MCP_EXTRA   JSON 数组字符串，每项声明一个额外 stdio MCP：
    #       {
    #         "name":  "server 名（工具前缀 / 冲突改名用）",
    #         "scope": "global | workspace"（默认 global）
    #         "command": "可执行文件（绝对路径或 PATH 中的名字）",
    #         "args":   ["arg1", "arg2"],
    #         "env":    {"KEY": "value"},        # 可选，附加环境变量
    #         "enabled": true,                    # 可选，默认 true
    #         "prompt": "引导文本",               # 可选，内联提示词
    #         "prompt_file": "relative/path.md",  # 可选，提示词文件（相对项目根）
    #       }
    #   配置项从 .env 读取（json 字符串）；解析失败只告警并跳过该项，
    #   不阻断 agent 启动。示例见 .env.example。
    # ------------------------------------------------------------------
    DEEPDEV_MCP_EXTRA: str = ""

    # ------------------------------------------------------------------
    # 日志（backend/logging 包）
    #
    #   DEEPDEV_LOG_LEVEL  控制台日志级别（DEBUG/INFO/WARNING/ERROR，默认 INFO）
    #   DEEPDEV_LOG_FILE   JSONL 日志文件路径（空 = 只打控制台；logs/ 已 gitignore）
    # ------------------------------------------------------------------
    DEEPDEV_LOG_LEVEL: str = "INFO"
    DEEPDEV_LOG_FILE: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore"
    )


settings = Settings()