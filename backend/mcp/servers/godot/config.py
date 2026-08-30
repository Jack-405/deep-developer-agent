"""godot-ai 接入配置。

本模块只负责三件事：

1. 路径解析（迁移友好，不写死绝对路径进项目文件）
2. workspace 是否为 Godot 项目的判定
3. `godot-ai attach` 启动参数构造

重要约定：

- godot-ai 是**黑盒进程**：本项目绝不 import godot_ai 内部代码，
  只通过 `uv run --project <dir> godot-ai attach` 的 stdio 与其交互。
- 路径分层：
    - godot-ai 源码：默认取约定相对路径 ``<deepdev 项目根>/vendor/godot-ai``
      （随 git 提交、随项目迁移）；可用环境变量 ``DEEPDEV_GODOT_AI_DIR`` 覆盖。
    - Godot 项目：默认自动探测 workspace 下的 ``project.godot``（含一层子目录）；
      可用环境变量 ``DEEPDEV_GODOT_PROJECT_PATH`` 显式指定。
"""

from __future__ import annotations

from pathlib import Path

from backend.config.settings import BASE_DIR, settings


def resolve_godot_ai_dir() -> Path:
    """godot-ai 源码目录：环境变量覆盖 > 约定相对路径 vendor/godot-ai。"""
    override = settings.DEEPDEV_GODOT_AI_DIR.strip()
    if override:
        return Path(override).expanduser().resolve()
    return BASE_DIR / "vendor" / "godot-ai"


def is_godot_ai_ready() -> bool:
    """godot-ai 目录就绪（存在 pyproject.toml 即认为可启动）。"""
    return (resolve_godot_ai_dir() / "pyproject.toml").is_file()


def _find_project_file(base: Path) -> Path | None:
    """在 base 及其一层子目录中探测 project.godot。"""
    direct = base / "project.godot"
    if direct.is_file():
        return direct

    if not base.is_dir():
        return None

    for child in sorted(base.iterdir()):
        if child.is_dir():
            candidate = child / "project.godot"
            if candidate.is_file():
                return candidate

    return None


def is_godot_workspace(workspace: str) -> bool:
    """判定 workspace 是否为 Godot 项目。

    显式配置（DEEPDEV_GODOT_PROJECT_PATH）优先；否则自动探测
    workspace 下（含一层子目录）是否存在 project.godot。
    """
    explicit = settings.DEEPDEV_GODOT_PROJECT_PATH.strip()
    if explicit:
        return (Path(explicit).expanduser().resolve() / "project.godot").is_file()

    return _find_project_file(Path(workspace).expanduser().resolve()) is not None


def build_attach_args() -> list[str]:
    """构造 `godot-ai attach` 的启动参数（不含 uv 可执行本身）。"""
    return [
        "run",
        "--project",
        str(resolve_godot_ai_dir()),
        "godot-ai",
        "attach",
        "--port",
        str(settings.DEEPDEV_GODOT_PORT),
        "--ws-port",
        str(settings.DEEPDEV_GODOT_WS_PORT),
        "--disable-telemetry",
    ]
