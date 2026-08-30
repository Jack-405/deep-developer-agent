# Deep Developer Agent

基于 `deepagents` 与 `langchain` 的终端 AI 开发助手。在命令行中以交互式 REPL 方式运行，
支持多轮对话、工作区切换，通过子智能体（planner / test）辅助完成复杂开发任务，
并通过 MCP 协议接入外部工具（Godot 游戏开发、Obsidian 笔记库等）。

## 特性

- **交互式 REPL**：多轮对话、工作区切换（`use` / `cd`）、历史归档
- **子智能体**：planner（复杂任务规划）/ test（开发结果验证）
- **MCP 集成**：内置 Godot / Obsidian 适配器，并支持**配置驱动接入任意 stdio MCP**（无需改代码）
- **记忆系统**：全局 → 项目 → 运行时三层记忆
- **启动量化**：内置日志系统，可分析启动耗时

## 快速开始

### 环境要求

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

### 安装

```bash
git clone <your-repo-url>
cd deep-developer-agent

# 方式一：uv（推荐）
uv sync

# 方式二：pip
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -e .
```

### 配置

```bash
copy .env.example .env           # Windows
cp .env.example .env             # Linux / macOS
```

编辑 `.env`，至少配置模型：

```env
MODEL_NAME=your-model-name
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=sk-your-api-key
```

### 启动

**方式一：wrapper 脚本（推荐，任意目录可用）**

```bash
deepdev [--workspace <path>] [--verbose]
```

- 脚本位于项目根：`deepdev.bat`（CMD）/ `deepdev.ps1`（PowerShell）
- 自动定位项目根下的 `.venv` 解释器，**不切换进程工作目录**，
  因此默认工作区 = 启动时的当前终端目录
- 首次使用将项目根加入 PATH（一次性）

**方式二：直接调用**

```bash
.venv\Scripts\python.exe -m cli [--workspace <path>] [--verbose]
```

### 启动参数

| 参数 | 说明 |
|---|---|
| `--workspace <path>` | 显式指定工作区（优先级最高） |
| `--verbose` | 输出 verbose 日志 |

## 工作区机制

- **默认工作区**：启动时终端所在目录（`CWD`）优先，
  其次回退到注册表记录的上次工作区，最后交互输入兜底
- **切换工作区**：REPL 内使用 `use <path>` 或 `cd <path>`，
  相对路径基于当前工作区解析；切换后 agent 与会话重建
- **常用命令**：`help` / `exit` / `quit` / `pwd` / `use <path>` / `cd <path>` / `workspace`

## MCP 集成

### 内置适配器（可选）

| 适配器 | 作用域 | 依赖 |
|---|---|---|
| Godot | workspace | `vendor/godot-ai`（[godot-ai](https://github.com/lstpsche/godot-ai)） |
| Obsidian | global | `obsidian-mcp` 二进制（[obsidian-mcp](https://github.com/lstpsche/obsidian-mcp)） |

第三方 MCP 源码/二进制**不进入本仓库**，由安装脚本拉取到 `vendor/<name>/`，
再在 `.env` 中配置路径。对应依赖未就绪时自动降级跳过，不影响核心功能。

### 配置驱动接入任意 MCP（无需改代码）

在 `.env` 中声明启动方式即可：

```env
DEEPDEV_MCP_EXTRA=[{"name":"my-mcp","scope":"global","command":"npx","args":["-y","@some/mcp-server"]}]
```

字段说明见 `.env.example`。支持 scope（global/workspace）、env、prompt、
prompt_file 等，解析失败只告警跳过，不阻断启动。

## Agent Skills（可选）

仓库**不内置任何 skill 内容**（`backend/skills/godot-skills-main/` 仅保留目录占位，
gitignore 隔离），由使用者自行配置：

1. 下载所需的 Agent Skills 仓库（如 **Codex Godot Skills**，可在 GitHub 搜索获取），
   把其中的 skill 目录放到 `backend/skills/godot-skills-main/` 下
   （每个 skill 目录需含合规的 `SKILL.md`，frontmatter 的 `name` 与目录名一致）。
2. 目前仅对 **Godot 项目**（工作区存在 `project.godot`）注入 Godot skills；
   其他项目类型暂不注入。
3. 未配置时自动降级跳过，不影响核心功能（`backend/skills/manager.py`
   是装配层代码，随仓库分发）。

## 项目结构

```
backend/    核心业务：agent 工厂、MCP 抽象层、记忆、技能、日志
cli/        CLI 包：入口、渲染、REPL、命令、会话、工作区解析
tests/      测试
scripts/    安装脚本（可选组件）
projects/   工作区注册表（运行时生成，gitignore 隔离）
vendor/     第三方 MCP 源码（不进入仓库，脚本拉取）
```

## 开发说明

- 运行测试：`.venv\Scripts\python.exe tests\test_xxx.py`（每个文件可独立运行）
- CLI 拆分结构：`main`（入口）/ `renderer`（渲染）/ `repl`（编排）/
  `commands`（命令）/ `session`（会话）/ `workspace`（工作区解析）
- 日志与启动量化：`backend/logging/`，`DEEPDEV_LOG_FILE` 开启 JSONL 落盘

## License

[MIT](LICENSE)
