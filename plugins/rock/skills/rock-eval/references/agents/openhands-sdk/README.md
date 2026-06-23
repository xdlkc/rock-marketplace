# OpenHands SDK Agent

## 定位
适配 OpenHands Software Agent SDK，源码在 `src/harbor/agents/installed/openhands_sdk.py`。保留工具模型和轨迹格式，同时显著降低运行时重量。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 优先于 `LLM_MODEL`。 | `src/harbor/agents/installed/openhands_sdk.py::OpenHandsSDK.create_run_agent_commands` |
| `agent.kwargs.reasoning_effort` / `load_skills` / `skill_paths` / `collect_token_ids` / `max_iterations` / `temperature` | SDK 运行参数。 | `src/harbor/agents/installed/openhands_sdk.py::OpenHandsSDK.__init__`；`create_run_agent_commands` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `agent.env.LLM_API_KEY` / `environment.env.LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 主要接入变量；`agent.env` 优先。 | `src/harbor/agents/installed/openhands_sdk.py::OpenHandsSDK.create_run_agent_commands` |
| `task.environment.mcp_servers` | 会序列化成 `MCP_SERVERS_JSON` 传给 runner。 | `src/harbor/agents/installed/openhands_sdk.py::OpenHandsSDK.create_run_agent_commands` |

## Harbor job YAML 样例
```yaml
jobs_dir: jobs/openhands-sdk
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
  - name: openhands-sdk
    model_name: openai/gpt-4.1
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env:
      LLM_API_KEY: ${OPENAI_API_KEY}
      LLM_BASE_URL: ${OPENAI_BASE_URL}
      LLM_MODEL: ${OPENAI_MODEL}
    kwargs:
      reasoning_effort: high
      load_skills: true
      skill_paths:
        - /root/.openhands-sdk/skills
        - /root/.agents/skills
      collect_token_ids: false
      max_iterations: 80
      temperature: 0.2

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-openhands-sdk.sh.j2`：创建 venv、安装 SDK 和写 runner script。

### 运行与产物入口
- `src/harbor/agents/installed/openhands_sdk.py::OpenHandsSDK.create_run_agent_commands`：环境变量、MCP、runner 启动。
- `OpenHandsSDK.populate_context_post_run`：读取 SDK 直接产出的 `trajectory.json`。

## 对 instance 的依赖要求
- 只要求 Python venv 能创建成功。
- 比完整 OpenHands 轻很多。

## 文档更新时优先关注
- `src/harbor/agents/installed/openhands_sdk.py`
- `src/harbor/agents/installed/install-openhands-sdk.sh.j2`

## 差异与取舍
### 优点
- 轻量。
- `agent.env` / `environment.env` 友好。

### 缺点
- 能力面仍弱于完整 OpenHands。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
