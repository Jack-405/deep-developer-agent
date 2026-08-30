"""Godot MCP 工具使用引导。

仅当当前工作区是 Godot 项目且 Godot MCP 工具已加载时注入。
工具名需与 vendor/godot-ai 实际暴露的工具保持一致。
"""

GODOT_PROMPT = """
Godot 编辑器工具（MCP）：

当前项目已挂载 Godot 编辑器 MCP 工具（godot-ai），可直接读取和修改
Godot 项目、场景、节点等。仅当任务确实需要编辑器能力时才使用它们。

常用核心工具：

- session_activate：激活/确认会话可用。
- editor_state：获取编辑器当前状态。
- scene_get_hierarchy：获取场景树（有深度参数，先用小值）。
- node_get_properties：读取节点属性（按需取属性，避免全量）。

使用建议：

- 先探测后修改：操作前先用 scene_get_hierarchy / node_get_properties
  了解场景与节点现状，再决定修改内容。
- 控制返回体积：有 depth / limit / offset 类参数时先使用较小的值；
  需要更多数据再按需翻页。
- 批量操作优先：能一次完成的批量操作不要拆成多次单独调用。
"""
