from __future__ import annotations

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, LocalShellBackend
from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfileConfig,
    register_harness_profile,
)
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.agent.agents.planner import build_planner_subagent
from backend.agent.agents.test import build_test_subagent
from backend.agent.middleware.media_sanitizer import build_media_sanitizer_middleware
from backend.agent.prompts.developer import build_system_prompt
from backend.config.settings import settings
from backend.logging import StartupTimer
from backend.mcp.client import mcp_manager
from backend.memory.manager import build_memory_middleware
from backend.skills.manager import build_skills_middleware
from backend.workspace.manager import workspace_manager


model_name = settings.MODEL_NAME
base_url = settings.LLM_BASE_URL
api_key = settings.LLM_API_KEY


# ---------------------------------------------------------------------------
# DeepAgents Profile
# ---------------------------------------------------------------------------

register_harness_profile(
    "openai",
    HarnessProfileConfig(
        general_purpose_subagent=GeneralPurposeSubagentProfile(
            enabled=False,
        ),
    ),
)


# ---------------------------------------------------------------------------
# Main Agent
# ---------------------------------------------------------------------------

async def create_agent(workspace: str | None = None):
    """
    创建 DeepDeveloper Agent。

    参数：
        workspace:
            工作区目录。
            如果没有提供，则使用 workspace_manager 当前注册的工作区。

    返回：
        DeepAgents compiled agent。
    """

    if workspace is None:
        workspace = workspace_manager.require_current()

    # 启动量化：create_agent 各阶段耗时打点（事件经 deepdev.startup 输出）。
    timer = StartupTimer()

    # -----------------------------------------------------------------------
    # Model
    # -----------------------------------------------------------------------

    model = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=SecretStr(api_key),
    )
    timer.checkpoint("agent.model")

    # -----------------------------------------------------------------------
    # Backend
    # -----------------------------------------------------------------------
    #
    # LocalShellBackend 已经同时提供：
    #
    #   文件操作：
    #       read_file
    #       write_file
    #       edit_file
    #       ls
    #       glob
    #       grep
    #
    #   Shell：
    #       execute
    #
    # virtual_mode=True 用于虚拟路径语义以及路径相关的 guardrail。
    #
    # 注意：
    # LocalShellBackend 不是安全沙箱。
    # execute 最终仍然是在宿主机进程上执行。
    #
    # 外层再包一层 CompositeBackend：
    #
    #   artifacts_root="/.deepdev"
    #
    # 使 deepagents 默认注入的 SummarizationMiddleware 将对话历史
    # 落盘到 <workspace>/.deepdev/conversation_history/{thread_id}.md，
    # 与运行时记忆 memory.md 同层，且已被 .gitignore 隔离。
    # 未命中路由的路径 → 所有操作仍走 LocalShellBackend，行为不变。
    #
    # skills_routes 由 build_skills_middleware 提供：把 skill 虚拟路径
    # 前缀（如 /godot-skills-main/）挂载到独立 backend，使模型 read_file
    # 能读到仓库内置 SKILL.md（渐进式披露）。非 Godot 项目时为空 dict。
    #
    skills_middleware, skills_routes = build_skills_middleware(workspace)

    backend = CompositeBackend(
        default=LocalShellBackend(
            root_dir=workspace,
            virtual_mode=True,
        ),
        routes=skills_routes,
        artifacts_root="/.deepdev",
    )

    # -----------------------------------------------------------------------
    # Media Sanitizer
    # -----------------------------------------------------------------------
    #
    # deepagents 的 read_file 对图片/音频等非文本文件返回多模态内容块
    # （base64 image_url）。若模型端点是纯文本模型（不支持视觉），这些块
    # 会导致 400 崩溃（"unknown variant `image_url`, expected `text`"）。
    #
    # 该中间件在模型调用前把所有消息中的非文本块替换为文本占位，保证请求
    # 永远是纯文本。
    #
    # 注意：deepagents 的子智能体（planner/test）不会继承主 agent 的自定义
    # middleware，必须显式传入 SubAgent["middleware"] 才会挂到子智能体自己
    # 的调用链上（否则子智能体验证时 read_file 读图片同样会 400）。此处先
    # 构建一次，主 agent 与两个子智能体共享同一个无状态实例。
    # 构造失败返回 None，不阻塞 agent 启动。
    #
    media_sanitizer = build_media_sanitizer_middleware()

    # -----------------------------------------------------------------------
    # Subagents
    # -----------------------------------------------------------------------
    #
    # DeepAgents 0.5.x 使用 SubAgent 配置注册子智能体。
    #
    # 不是：
    #
    #     plan_agent=...
    #
    # 而是：
    #
    #     subagents=[...]
    #
    # planner：复杂任务执行前制定执行计划。
    # test：开发完成后验证结果与效果。
    #
    # 子代理显式传 tools=[]（A1）：deepagents 的 SubAgent 只要 spec 含
    # "tools" 键就不再继承主 agent 的 MCP 工具（graph.py 里
    # `spec.get("tools") if "tools" in spec else tools`），避免每轮请求
    # 携带 43+ 个 MCP 工具 schema 的 token 开销。子代理的文件操作与
    # execute 能力由 FilesystemMiddleware（继承主 agent 的 backend）
    # 提供，不依赖 tools 参数，功能不受影响。
    #
    subagent_middleware = [media_sanitizer] if media_sanitizer else None
    planner_subagent = build_planner_subagent(
        model, middleware=subagent_middleware, tools=[]
    )
    test_subagent = build_test_subagent(
        model, middleware=subagent_middleware, tools=[]
    )

    # -----------------------------------------------------------------------
    # Memory
    # -----------------------------------------------------------------------
    #
    # 记忆中间件按「全局 → 项目 → 运行时」三层加载记忆文件：
    #
    #   1. 全局：backend/memory/global/AGENTS.md（随 deepdev 分发，git 管理）
    #   2. 项目：<workspace>/AGENTS.md（随项目仓库走，git 管理）
    #   3. 运行时：<workspace>/.deepdev/memory.md（gitignore 隔离）
    #
    # 切换工作区会重建本 agent，记忆随之自动刷新，无需额外处理。
    # 记忆故障（缺文件、backend 异常）不会阻塞 agent 启动：
    # build_memory_middleware 内部容错，返回 None 时跳过中间件。
    #
    memory_middleware = build_memory_middleware(workspace)
    timer.checkpoint("agent.backend")

    # -----------------------------------------------------------------------
    # Skills
    # -----------------------------------------------------------------------
    #
    # 仓库内置 Agent Skills（backend/skills/）渐进式披露：
    #   - middleware 把 skill 的 name/description/path 注入 system prompt；
    #   - 模型按需用 read_file 读取 SKILL.md 全文（路径经上面 skills_routes
    #     路由到仓库 skills 目录）；
    #   - 仅 Godot 项目注入；构造失败返回 None，不阻塞 agent 启动。
    #

    # -----------------------------------------------------------------------
    # MCP 工具
    # -----------------------------------------------------------------------
    #
    # mcp_manager 遍历注册表（registry.build_registry()），对每个 server 判定
    # enabled() + ready() + applicable(workspace) 后懒启动会话并聚合工具：
    #   - godot：workspace 作用域，仅 Godot 项目（存在 project.godot）加载；
    #   - obsidian：global 作用域，vault 配置存在即加载；
    #   - 通用 MCP：由 DEEPDEV_MCP_EXTRA 配置声明，无需改代码。
    #
    # 工具名冲突由 mcp_manager 内部按注册表顺序处理（后加载方加
    # "<server>_" 前缀）。任何失败（依赖缺失、启动失败、工具加载失败）
    # 都会跳过对应 server 返回空列表，不阻断 agent 启动 —— MCP 集成
    # 缺失时降级为普通开发 agent。
    #
    loaded_specs, mcp_tools = await mcp_manager.collect(workspace)
    timer.checkpoint("agent.mcp")

    # -----------------------------------------------------------------------
    # Main Agent
    # -----------------------------------------------------------------------
    #
    # 系统提示词按 section 组装：
    #   base → subagents → mcp（→ 各实际加载的 MCP server 引导）
    # 仅当某个 server 实际加载了工具时注入其引导，未加载的 server 不带。
    #
    # middleware 组装：memory / skills / media_sanitizer 依次排在
    # deepagents 默认基础栈（TodoList → Skills → Filesystem → SubAgent →
    # Summarization → PatchToolCalls）之后、尾栈（PromptCaching 等）之前，
    # 对主 agent 与子代理（planner/test）共用调用链同时生效——后两者的
    # media_sanitizer 已在构建 SubAgent 时显式传入（见上文 Subagents 段）。
    #
    mcp_sections = [
        section
        for section in (spec.build_prompt() for spec in loaded_specs)
        if section
    ]
    system_prompt = build_system_prompt(mcp_sections=mcp_sections)

    agent = create_deep_agent(
        model=model,
        backend=backend,
        system_prompt=system_prompt,
        subagents=[planner_subagent, test_subagent],
        middleware=(
            ([memory_middleware] if memory_middleware else [])
            + ([skills_middleware] if skills_middleware else [])
            + ([media_sanitizer] if media_sanitizer else [])
        ),
        tools=mcp_tools or None,
    )
    timer.checkpoint("agent.compile")
    timer.summary(name="agent.create.total", workspace=workspace)

    return agent