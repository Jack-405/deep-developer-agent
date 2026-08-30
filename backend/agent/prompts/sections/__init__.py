"""系统提示词 sections 包。

每个 section 负责一类相对独立的内容：

- base.py：主 Agent 基础行为规范
- subagents.py：子智能体（planner / test）路由规范
- mcp.py：通用 MCP 集成工具使用原则
- godot.py：Godot MCP 工具引导（新增 MCP 时在此目录加对应模块）

组装入口在 backend.agent.prompts.developer.build_system_prompt。
"""
