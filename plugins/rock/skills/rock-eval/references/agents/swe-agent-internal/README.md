# SWE-Agent Internal

## 定位
`swe-agent-internal` 现在是 `swe-agent` 的兼容别名，工厂会直接映射到 `src/harbor/agents/installed/swe_agent/agent.py::SweAgent`。内部预处理模式由 OSS 依赖和运行脚本能力探测触发，不再有独立 `SweAgentInternal` 类。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 必填。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.create_run_agent_commands` |
| `agent.kwargs.per_instance_cost_limit` / `total_cost_limit` / `max_input_tokens` / `temperature` / `top_p` | 映射到 `--agent.model.*`。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.CLI_FLAGS` |
| `agent.kwargs.api_key` / `api_base` / `max_iterations` / `max_tokens` / `num_retries` / `tools_parse_function` / `max_observation_length` | 统一版 CLI flag。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.CLI_FLAGS` |
| `agent.kwargs.sweagent_config` / `completion_kwargs` / `full_history` | Python 侧组合参数。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.__init__`；`create_run_agent_commands` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `environment.env.INSTANCE_ID` / `DATASET` / `SPLIT` | 内部预处理链路的关键环境变量。 | `src/harbor/agents/installed/swe_agent/run.sh.j2` |
| `environment.oss_deps` | 预处理模式通常准备 `/tmp/shared/swe-preprocess.tar.gz` 和 `/tmp/shared/SWE-agent.tar.gz`。 | `src/harbor/agents/installed/swe_agent/install.sh.j2` |
| `OSS_*` | setup 阶段会透传到环境。 | `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.setup` |

## Harbor job YAML 样例
```yaml
# OpenAI-compatible 路径可把 OPENAI_API_KEY / OPENAI_BASE_URL 放在 environment.env；
# OSS_* 和部分非 OpenAI fallback 仍主要来自宿主机环境。
jobs_dir: jobs/swe-agent-internal
n_attempts: 1
timeout_multiplier: 1.0
agent_setup_timeout_multiplier: 3.0
orchestrator:
  type: local
  n_concurrent_trials: 1
  quiet: false

environment:
  type: docker
  force_build: true
  delete: true
  env:
    INSTANCE_ID: django__django-13410
    DATASET: princeton-nlp/SWE-bench_Verified
    SPLIT: test
  kwargs: {}
  oss_deps:
    deps/swe-preprocess.latest.tar.gz: /tmp/shared/swe-preprocess.tar.gz
    deps/SWE-agent-v1.1.0-0323.tar.gz: /tmp/shared/SWE-agent.tar.gz

agents:
  - name: swe-agent-internal
    model_name: openai/glm-5
    override_timeout_sec: 2400
    override_setup_timeout_sec: 2400
    max_timeout_sec: 3600
    env: {}
    kwargs:
      per_instance_cost_limit: "0"
      total_cost_limit: "0"
      max_input_tokens: "0"
      temperature: "1.0"
      top_p: "0.95"
      api_key: ${OPENAI_API_KEY}
      api_base: ${OPENAI_BASE_URL}
      max_iterations: 200
      num_retries: 4
      tools_parse_function: function_calling
      max_observation_length: 10000
      sweagent_config: anthropic
      max_tokens: 8192
      completion_kwargs:
        response_format: json_object
      full_history: true

datasets:
  - registry:
    split: test
    name: princeton-nlp/SWE-bench_Verified
    version: test
    task_names:
      - django__django-13410
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/swe_agent/install.sh.j2`：OSS 依赖校验、glibc 兼容、解压 `swe-preprocess` 与 SWE-agent。

### 运行与产物入口
- `src/harbor/agents/installed/swe_agent/agent.py::SweAgent.create_run_agent_commands`：预处理后的 repo / config_dict 驱动。
- `src/harbor/agents/installed/swe_agent/agent.py::convert_and_save_trajectory`：ATIF 转换。

## 对 instance 的依赖要求
- 实例要求最重：OSS 依赖、`jq`、`git`、`swe-preprocess`、benchmark 元数据都要齐。
- 主要目标是内部复杂 benchmark。

## 文档更新时优先关注
- `src/harbor/agents/installed/swe_agent/agent.py`
- `src/harbor/agents/installed/swe_agent/install.sh.j2`
- `src/harbor/agents/installed/swe_agent/run.sh.j2`

## 差异与取舍
### 优点
- 最贴合内部 SWE benchmark。
- 对 Alpine / 老 glibc 有显式兼容。

### 缺点
- 依赖链极长。
- 几乎不适合通用软件工程任务。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
