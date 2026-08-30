"""
DeepDeveloper CLI 包。

将原本单一的 cli.py 按职责拆分为：

- main.py      入口：参数解析、依赖组装、启动 REPL
- renderer.py  渲染层：颜色、状态条、事件分发（纯展示）
- workspace.py 工作区：解析优先级、启动横幅
- commands.py  命令：内置命令注册表与分发
- session.py   会话：消息生命周期与单轮任务执行
- repl.py      编排：读输入 → 命令 / Agent 分流

拆分原则：行为零变化，纯结构性重构。
"""
