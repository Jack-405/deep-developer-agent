# godot-ai 接入（MCP）

deepdev 作为 MCP 客户端，经 godot-ai 的 stdio 桥接入 Godot 编辑器。

## 链路

```
deepdev REPL
 └─ MCPManager（REPL 级单例，backend/mcp/client.py；godot 为注册表中
     workspace 作用域 server，GODOT_SPEC 见 backend/mcp/servers/godot/spec.py）
      └─ uv run --project vendor/godot-ai godot-ai attach --port 8000 --ws-port 9500 --disable-telemetry
           └─ 共享 HTTP 后端 :8000 → WebSocket :9500 → Godot 插件（addons/godot_ai）
```

godot-ai 是黑盒进程：本项目绝不 import 其内部代码，只走 MCP 协议。

## 启用条件

1. `uv sync`（安装 mcp、langchain-mcp-adapters 依赖）
2. workspace 是 Godot 项目（存在 `project.godot`，自动探测，含一层子目录）
3. Godot 编辑器插件已启用（项目 `addons/godot_ai`）

任一条不满足则降级为普通开发 agent（无 Godot 工具），不阻断 CLI 启动。

## 配置（环境变量 / .env，全部可选）

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPDEV_GODOT_ENABLED` | `true` | 设为 `false` 关闭 Godot 集成 |
| `DEEPDEV_GODOT_AI_DIR` | `vendor/godot-ai`（相对项目根） | godot-ai 源码目录覆盖 |
| `DEEPDEV_GODOT_PROJECT_PATH` | 空（自动探测） | 显式指定 Godot 项目目录 |
| `DEEPDEV_GODOT_PORT` | `8000` | 共享后端 HTTP 端口 |
| `DEEPDEV_GODOT_WS_PORT` | `9500` | Godot 插件 WebSocket 端口 |

项目文件不写绝对路径：相对路径约定 + 环境变量覆盖，随仓库迁移零改动。

## 验证

```powershell
uv sync
uv run --project vendor/godot-ai godot-ai attach --version   # 确认启动链路
```
