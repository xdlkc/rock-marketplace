# Mini SWE Agent

## 定位
轻量 repo repair agent，源码在 `src/harbor/agents/installed/mini_swe_agent.py`。保留 benchmark 友好的轨迹和 cost 统计，比完整 SWE-agent 轻。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 要求 `provider/model`。 | `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.create_run_agent_commands` |
| `agent.kwargs.cost_limit` | 映射 `--cost-limit`。 | `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.CLI_FLAGS` |
| `agent.kwargs.reasoning_effort` | 会写到 `model.model_kwargs.extra_body.reasoning_effort`。 | `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.__init__`；`create_run_agent_commands` |
| `agent.kwargs.config_file` | 读取自定义 YAML 并写入容器。 | `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.__init__`；`create_run_agent_commands` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `MSWEA_API_KEY` | 优先使用。 | `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.create_run_agent_commands` |
| `OPENAI_API_BASE` | 可选 API base。 | `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.create_run_agent_commands` |
| `OSS_*` | setup 阶段会自动透传到环境，供 OSS 依赖访问。 | `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.setup` |

## Harbor job YAML 样例
```yaml
# MSWEA_API_KEY 或 provider API key 可放在 environment.env 共享，也可放在 agent.env 覆盖。
jobs_dir: jobs/mini-swe-agent
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
    MSWEA_API_KEY: ${MSWEA_API_KEY}
    OPENAI_API_BASE: ${OPENAI_API_BASE}
  kwargs: {}

agents:
  - name: mini-swe-agent
    model_name: anthropic/claude-3-5-sonnet-20241022
    override_timeout_sec: 1800
    override_setup_timeout_sec: 1200
    max_timeout_sec: 3600
    env:
      MSWEA_API_KEY: ${MSWEA_API_KEY}
    kwargs:
      cost_limit: "0"
      reasoning_effort: high
      config_file: null

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-mini-swe-agent.sh.j2`：系统包、uv、mini-swe-agent 与 AgentTrack wrapper。

### 运行与产物入口
- `src/harbor/agents/installed/mini_swe_agent.py::MiniSweAgent.create_run_agent_commands`：配置与 CLI 启动。
- `MiniSweAgent.populate_context_post_run`：原始轨迹转 ATIF。

## 对 instance 的依赖要求
- 更适合 repo repair / benchmark。
- OSS 依赖访问时会用到 `OSS_*`。

## 文档更新时优先关注
- `src/harbor/agents/installed/mini_swe_agent.py`
- `src/harbor/agents/installed/install-mini-swe-agent.sh.j2`
- `tests/unit/agents/installed/test_mini_swe_agent.py`

## 差异与取舍
### 优点
- SWE 能力和轻量安装比较平衡。
- `agent.env` / `environment.env` 兼容好。

### 缺点
- 最佳场景集中在 repo repair。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
