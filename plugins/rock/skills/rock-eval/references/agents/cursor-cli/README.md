# Cursor CLI Agent

## 定位
适配 `cursor-agent`，源码在 `src/harbor/agents/installed/cursor_cli.py`。实现很薄，重点在命令执行和 MCP 注入。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 实现要求 `provider/model`；仓库里的旧样例 `sonnet-4` 已过时。 | `src/harbor/agents/installed/cursor_cli.py::CursorCli.create_run_agent_commands` |
| `agent.kwargs.mode` | `plan|ask|agent`。 | `src/harbor/agents/installed/cursor_cli.py::CursorCli.CLI_FLAGS` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `CURSOR_API_KEY` | 必填，前置只看宿主机环境。 | `src/harbor/agents/installed/cursor_cli.py::CursorCli.create_run_agent_commands` |
| `task.environment.mcp_servers` | 会写到 `~/.cursor/mcp.json`。 | `src/harbor/agents/installed/cursor_cli.py::_build_register_mcp_servers_command` |

## Harbor job YAML 样例
```yaml
# 宿主机先导出：CURSOR_API_KEY。
jobs_dir: jobs/cursor-cli
n_attempts: 1
timeout_multiplier: 1.0
orchestrator:
  type: local
  n_concurrent_trials: 1
  quiet: false

environment:
  type: docker
  force_build: true
  delete: true
  env: {}
  kwargs: {}

agents:
  - name: cursor-cli
    model_name: anthropic/claude-sonnet-4-5
    override_timeout_sec: 1800
    override_setup_timeout_sec: 300
    max_timeout_sec: 3600
    env: {}
    kwargs:
      mode: agent

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-cursor-cli.sh.j2`：执行官方安装脚本。

### 运行与产物入口
- `src/harbor/agents/installed/cursor_cli.py::CursorCli.create_run_agent_commands`：MCP 配置与 CLI 启动。

## 对 instance 的依赖要求
- 更适合常规 glibc Linux。
- task 语言依赖仍由实例负责。

## 文档更新时优先关注
- `src/harbor/agents/installed/cursor_cli.py`
- `src/harbor/agents/installed/install-cursor-cli.sh.j2`
- `tests/unit/agents/installed/test_cursor_cli_mcp.py`

## 差异与取舍
### 优点
- 轻量。
- 适合快速产品对比。

### 缺点
- 没有 Harbor 侧 ATIF。
- 凭证注入不灵活。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
