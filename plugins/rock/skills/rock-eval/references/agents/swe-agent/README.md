# SWE-Agent

## 定位
适配完整 SWE-agent，源码在 `src/harbor/agents/installed/swe_agent/agent.py`。会把原始 `.traj` 转成 ATIF。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 必填。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.create_run_agent_commands` |
| `agent.kwargs.per_instance_cost_limit` / `total_cost_limit` / `max_input_tokens` / `temperature` / `top_p` | 映射到 `--agent.model.*`。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.CLI_FLAGS` |
| `agent.kwargs.max_iterations` / `max_tokens` / `num_retries` / `api_key` / `api_base` / `tools_parse_function` / `max_observation_length` | 统一版新增 CLI flag。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.CLI_FLAGS` |
| `agent.kwargs.sweagent_config` / `completion_kwargs` / `full_history` | Python 侧组合参数。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.__init__`；`create_run_agent_commands` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | `openai/*` 与 OpenAI-compatible 路径可从 `agent.env` 或 `environment.env` 读取。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.create_run_agent_commands` |
| `ANTHROPIC_API_KEY` / `TOGETHER_API_KEY` / `SWEAGENT_CONFIG` | 当前非 OpenAI-compatible fallback 主要读宿主机环境；也可优先用 `api_key` / `api_base` / `sweagent_config` kwargs 显式传入。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.create_run_agent_commands` |

## Harbor job YAML 样例
```yaml
# openai/* 路径可把 OPENAI_API_KEY / OPENAI_BASE_URL 放在 environment.env。
jobs_dir: jobs/swe-agent
n_attempts: 1
timeout_multiplier: 1.0
agent_setup_timeout_multiplier: 2.0
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
  - name: swe-agent
    model_name: openai/gpt-4.1
    override_timeout_sec: 2400
    override_setup_timeout_sec: 1800
    max_timeout_sec: 3600
    env: {}
    kwargs:
      per_instance_cost_limit: "0"
      total_cost_limit: "0"
      max_input_tokens: "0"
      temperature: "0.2"
      top_p: "0.95"

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/swe_agent/install.sh.j2`：uv venv、clone SWE-agent、wrapper、AgentTrack。

### 运行与产物入口
- `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.create_run_agent_commands`：problem statement、repo 选择、CLI 启动。
- `SweAgent.populate_context_post_run`：`.traj` 转 ATIF。

## 对 instance 的依赖要求
- 强依赖 git repo 语义。
- 更适合 SWE-bench / repo repair。

## 文档更新时优先关注
- `src/harbor/agents/installed/swe_agent/agent.py`
- `src/harbor/agents/installed/swe_agent/install.sh.j2`

## 差异与取舍
### 优点
- SWE benchmark 适配成熟。
- ATIF 已内置。

### 缺点
- 环境耦合重。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
