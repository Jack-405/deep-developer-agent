"""Obsidian MCP 工具使用引导。

仅当 obsidian-mcp 已加载（OBSIDIAN_BIN 可定位且 OBSIDIAN_VAULT_PATH
存在）时注入。工具名与 obsidian-mcp v2.5 实际暴露的工具保持一致；
若与其它 MCP 工具撞名，冲突方会被加上 ``obsidian_`` 前缀。
"""

OBSIDIAN_PROMPT = """
Obsidian 笔记库工具（MCP）：

已挂载 obsidian-mcp，可直接读写 Obsidian vault（笔记库）。这些工具
运行在独立的 obsidian-mcp 进程中，直接操作磁盘上的 vault 目录，与
当前工作区的文件工具是两套独立通道。

工具分工（重要）：

- 笔记操作：note_read / note_create / note_write / note_insert /
  note_patch / note_delete / note_move（vault 内的笔记 CRUD）
- 检索：search_text（全文检索）/ search_regex / search_metadata（标签/
  frontmatter 查询）
- 结构：vault_list / vault_info / note_inspect / wikilinks（双链图谱）
- 其他：frontmatter（属性读写）、periodic（日记/周记等周期笔记）、
  open_in_obsidian（在 Obsidian 应用中打开）

路径语义（容易踩坑）：

- 所有工具的参数 path 都是 **vault 相对路径**（如 "Projects/xxx.md"），
  不是文件系统绝对路径，也不是本工作区的虚拟路径。vault 根目录用空串。
- 笔记内容为 Markdown，可选 YAML frontmatter；frontmatter 字段可用
  frontmatter 工具单独读写。

边界声明：

- obsidian 工具只能读写 vault 内的笔记，无法访问 vault 之外的路径
  （server 自带防护，拒绝绝对路径与 ../ 逃逸）。
- 项目代码、配置文件等仓库内文件的读写仍用 read_file / write_file /
  edit_file / grep 等文件工具，不要用 obsidian 工具。

使用建议：

- 先检索后写入：写入前用 search_text / note_read 确认目标笔记现状。
- 控制返回体积：search_text / note_read_many 等有 limit / max_files /
  max_bytes 参数，先用较小值，需要更多再翻页。
- 若工具名带 obsidian_ 前缀（与其它 MCP 冲突时），调用时使用带前缀
  的名字。
"""