# Codex Agent

## 定位
适配 OpenAI Codex CLI，源码在 `src/harbor/agents/installed/codex.py`。支持 MCP、skills、会话日志转 ATIF。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 必填，常用 `openai/<model>`。 | `src/harbor/agents/installed/codex.py::Codex.create_run_agent_commands` |
| `agent.kwargs.reasoning_effort` | 默认 `high`，以 `-c model_reasoning_effort=<value>` 形式传递。 | `src/harbor/agents/installed/codex.py::Codex.CLI_FLAGS` |
| `agent.kwargs.reasoning_summary` | `auto|concise|detailed|none`。 | `src/harbor/agents/installed/codex.py::Codex.CLI_FLAGS` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | Codex CLI 凭证与兼容网关。 | `src/harbor/agents/installed/codex.py::Codex.create_run_agent_commands` |
| `task.environment.mcp_servers` / `skills_dir` | 会写到 `$CODEX_HOME/config.toml` 与 `$HOME/.agents/skills`。 | `src/harbor/agents/installed/codex.py::_build_register_mcp_servers_command`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
# OPENAI_API_KEY / OPENAI_BASE_URL 可放在 environment.env 共享，也可放在 agent.env 覆盖。
jobs_dir: jobs/codex
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
  env:
    OPENAI_API_KEY: ${OPENAI_API_KEY}
    OPENAI_BASE_URL: ${OPENAI_BASE_URL}
  kwargs: {}

agents:
  - name: codex
    model_name: openai/o3
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env:
      OPENAI_BASE_URL: ${OPENAI_BASE_URL}
    kwargs:
      reasoning_effort: high
      reasoning_summary: detailed

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-codex.sh.j2`：Alpine 用 apk+npm，glibc 用 nvm。

### 运行与产物入口
- `src/harbor/agents/installed/codex.py::Codex.create_run_agent_commands`：auth、config、CLI 启动。
- `src/harbor/agents/installed/codex.py::Codex.populate_context_post_run`：session JSONL 转 ATIF。

## 对 instance 的依赖要求
- Node / npm 安装能力。
- Alpine 与 glibc 都有显式兼容分支。

## 文档更新时优先关注
- `src/harbor/agents/installed/codex.py`
- `src/harbor/agents/installed/install-codex.sh.j2`
- `tests/unit/agents/installed/test_codex_*`

## 差异与取舍
### 优点
- ATIF 完整。
- MCP / skills 接入清楚。

### 缺点
- 调参面相对集中在 reasoning。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
