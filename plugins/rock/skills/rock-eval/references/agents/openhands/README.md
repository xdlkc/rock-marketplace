# OpenHands Agent

## 定位
适配完整 OpenHands runtime，源码在 `src/harbor/agents/installed/openhands.py`。是仓库里功能最全、依赖也最重的通用 runtime 之一。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 优先于 `LLM_MODEL` / `ANTHROPIC_MODEL`。 | `src/harbor/agents/installed/openhands.py::OpenHands.create_run_agent_commands` |
| `agent.kwargs.disable_tool_calls` | 控制 `LLM_NATIVE_TOOL_CALLING`。 | `src/harbor/agents/installed/openhands.py::OpenHands.ENV_VARS`；`OpenHands.__init__` |
| `agent.kwargs.reasoning_effort` / `temperature` / `max_iterations` / `caching_prompt` / `top_p` / `num_retries` / `max_budget_per_task` / `drop_params` / `disable_vision` | 全部通过 `ENV_VARS` 映射。 | `src/harbor/agents/installed/openhands.py::OpenHands.ENV_VARS` |
| `agent.kwargs.trajectory_config.raw_content` | 要求同时 `disable_tool_calls=true`。 | `src/harbor/agents/installed/openhands.py::OpenHands.__init__` |
| `agent.kwargs.api_base` / `model_info` / `git_version` | base URL、token limits、从 Git 安装。 | `src/harbor/agents/installed/openhands.py::OpenHands.__init__`；`_template_variables`；`create_run_agent_commands` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `agent.env.LLM_API_KEY` / `environment.env.LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_VERSION` | OpenHands runtime 通用接入变量；`agent.env` 优先。 | `src/harbor/agents/installed/openhands.py::OpenHands.create_run_agent_commands` |
| `OPENHANDS_*` | 会去掉前缀后透传给运行时。 | `src/harbor/agents/installed/openhands.py::OpenHands.create_run_agent_commands` |
| `task.environment.mcp_servers` | 写入 `~/.openhands/config.toml`。 | `src/harbor/agents/installed/openhands.py::_build_mcp_config_toml` |

## Harbor job YAML 样例
```yaml
# LLM_API_KEY / LLM_BASE_URL 可放在 environment.env 共享，也可放在 agent.env 覆盖。
jobs_dir: jobs/openhands
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
    OPENHANDS_LOG_LEVEL: INFO
  kwargs: {}

agents:
  - name: openhands
    model_name: openai/gpt-5
    override_timeout_sec: 2400
    override_setup_timeout_sec: 1800
    max_timeout_sec: 3600
    env:
      LLM_API_KEY: ${OPENAI_API_KEY}
      LLM_BASE_URL: ${OPENAI_BASE_URL}
      LLM_MODEL: ${OPENAI_MODEL}
    kwargs:
      disable_tool_calls: false
      reasoning_effort: high
      temperature: "0.2"
      max_iterations: 80
      caching_prompt: true
      top_p: "0.95"
      num_retries: 3
      max_budget_per_task: "15"
      drop_params: false
      disable_vision: false
      api_base: ${OPENAI_BASE_URL}
      model_info:
        max_input_tokens: 128000
        max_output_tokens: 8192
      trajectory_config:
        raw_content: false
      git_version: null

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-openhands.sh.j2`：Python 3.13、uv、venv、OpenHands 安装。

### 运行与产物入口
- `src/harbor/agents/installed/openhands.py::OpenHands.create_run_agent_commands`：MCP、runtime env、CLI 启动。
- `OpenHands.populate_context_post_run`：event / completion 日志转 ATIF。

## 对 instance 的依赖要求
- 需要 Python 3.13、tmux、build-essential。
- 更适合 repo / tool-heavy 任务。
- 自托管模型最好补 `model_info`。

## 文档更新时优先关注
- `src/harbor/agents/installed/openhands.py`
- `src/harbor/agents/installed/install-openhands.sh.j2`
- `tests/unit/agents/installed/test_openhands_*`

## 差异与取舍
### 优点
- 功能面最全之一。
- `agent.env` / `environment.env` 兼容好。

### 缺点
- 安装和运行都重。
- 参数复杂。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
