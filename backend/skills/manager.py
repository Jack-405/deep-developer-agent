"""Skills 组装层。

把使用者自备的 Agent Skills（backend/skills/godot-skills-main/ 下
由用户放置的技能目录）装配为 deepagents 的 SkillsMiddleware，并为
agent 的文件 backend 提供路由，使模型可以用 read_file 按需读取
SKILL.md 全文（渐进式披露）。

与 deepagents 0.6.x 机制对应的关键设计：

1. SkillsMiddleware 只负责把每个 skill 的 name/description/path 注入
   system prompt；SKILL.md 全文由模型调用 read_file 工具自行读取，
   middleware 不做任何文件读取拦截。

2. skill 内容由使用者自行下载放置到 backend/skills/godot-skills-main/
   （gitignore 隔离，不入库），而 workspace 是用户任意项目目录（可能
   在仓库之外）。当模型按 system prompt 中的路径 read_file 时，必须能
   路由到 skill 目录，
   因此通过 CompositeBackend 的路径路由把 skill 虚拟前缀挂载到
   独立的 FilesystemBackend 上。

3. 两个 backend 的 root 必须与路径视图自洽：

   - SkillsMiddleware backend:
       root=<BASE>/backend/skills（virtual_mode=True）
       sources=[("/godot-skills-main/", "Godot")]
       → 展示路径 "/godot-skills-main/<skill>/SKILL.md"
   - CompositeBackend 路由:
       前缀 "/godot-skills-main/" → backend
       root=<BASE>/backend/skills/godot-skills-main（virtual_mode=True）
       → 剥离前缀后 "/<skill>/SKILL.md" 映射到
         <root>/<skill>/SKILL.md，与展示路径完全一致

4. 加载策略：仅当 workspace 是 Godot 项目（存在 project.godot）时
   注入 Godot skill；其他项目不注入（与 MCP 注册表中 godot server 的
   workspace 判定同源）。

5. 容错约定：任何异常（路径缺失、backend 构造失败）返回
   (None, {})，skills 故障绝不阻塞 agent 启动。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 项目根：backend/skills/manager.py 向上三级（与 backend/config/settings.py
# 的 BASE_DIR 同值）。不 import settings，避免在受限环境（无 asyncio）中
# 无法导入本模块 —— 纯路径函数保持零第三方依赖，可独立测试。
BASE_DIR = Path(__file__).resolve().parents[2]

# skills 根目录（内容由用户自备放置，gitignore 隔离不入库；本文件随仓库分发）
SKILLS_ROOT = BASE_DIR / "backend" / "skills"

# godot-skills 子目录名（用户放置的 Codex Godot Skills 仓库）
GODOT_SKILLS_DIR = "godot-skills-main"

# skill 在 agent 文件视图中的虚拟路径前缀（与 SkillsMiddleware 展示路径一致）
GODOT_SKILLS_ROUTE_PREFIX = f"/{GODOT_SKILLS_DIR}/"

# SkillsMiddleware 的 source 显示标签
GODOT_SKILLS_LABEL = "Godot"


def resolve_skills_dir() -> Path:
    """仓库内置 skills 根目录（纯路径，无 deepagents 依赖，可独立测试）。"""
    return SKILLS_ROOT


def _godot_skills_dir() -> Path:
    return SKILLS_ROOT / GODOT_SKILLS_DIR


def _is_godot_workspace(workspace: str) -> bool:
    """复用 godot-ai 接入的 workspace 判定（存在 project.godot）。"""
    from backend.mcp.servers.godot.config import is_godot_workspace

    return is_godot_workspace(workspace)


def _build_skills_middleware(workspace: str) -> tuple[Any | None, dict[str, Any]]:
    """构造 SkillsMiddleware 与其配套的 CompositeBackend 路由（不捕获异常）。

    调用方负责容错包装。
    """
    from deepagents.backends import FilesystemBackend
    from deepagents.middleware import SkillsMiddleware

    skills_root = resolve_skills_dir()
    godot_skills = _godot_skills_dir()

    if not skills_root.is_dir() or not godot_skills.is_dir():
        return None, {}

    # SkillsMiddleware 自己的 backend：root=skills 根，sources 指向
    # godot-skills-main 子目录 → 展示路径带 "/godot-skills-main/" 前缀。
    skills_backend = FilesystemBackend(
        root_dir=skills_root,
        virtual_mode=True,
    )
    middleware = SkillsMiddleware(
        backend=skills_backend,
        sources=[(GODOT_SKILLS_ROUTE_PREFIX, GODOT_SKILLS_LABEL)],
    )

    # agent 文件 backend 的路由：前缀 "/godot-skills-main/" → root 为
    # godot-skills-main 目录的独立 backend。CompositeBackend 剥离前缀后
    # 转发 "/<skill>/SKILL.md"，virtual_mode 映射到
    # <godot_skills>/<skill>/SKILL.md —— 与展示路径自洽。
    route_backend = FilesystemBackend(
        root_dir=godot_skills,
        virtual_mode=True,
    )
    routes = {GODOT_SKILLS_ROUTE_PREFIX: route_backend}

    return middleware, routes


def build_skills_middleware(workspace: str | None = None) -> tuple[Any | None, dict[str, Any]]:
    """构建 skills 中间件与配套路由。

    参数：
        workspace: 工作区路径；None 时回退到 workspace_manager 当前工作区。

    返回：
        (middleware | None, routes)：
            middleware —— SkillsMiddleware 实例；非 Godot 项目或构造失败为 None。
            routes —— 供 factory 合并进 CompositeBackend 的路由表
            （{前缀: backend}）；未启用时为空 dict。

    任何异常都不会向外抛出 —— skills 故障绝不阻塞 agent 启动。
    """
    if workspace is None:
        try:
            from backend.workspace.manager import workspace_manager

            workspace = workspace_manager.require_current()
        except Exception:
            return None, {}

    # 仅 Godot 项目注入 Godot skill（与 MCP 注册表 godot server 判定同源）
    try:
        if not _is_godot_workspace(workspace):
            return None, {}
    except Exception:
        return None, {}

    try:
        return _build_skills_middleware(workspace)
    except Exception:
        return None, {}
