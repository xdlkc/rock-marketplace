# Terminus-2 Agent

## 定位
Harbor 原生 shell-first agent，源码在 `src/harbor/agents/terminus_2/terminus_2.py`。通过 tmux 驱动终端，支持 MCP、skills、总结子代理和完整 ATIF 轨迹。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 必填；自托管模型通常还要配 `model_info`。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2.__init__`；`Terminus2._resolve_model_info` |
| `agent.kwargs.max_turns` | 最大回合数。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2.__init__` |
| `agent.kwargs.parser_name` | `json` 或 `xml`。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2._get_parser`；`_get_prompt_template_path` |
| `agent.kwargs.api_base` / `temperature` / `reasoning_effort` / `max_thinking_tokens` / `use_responses_api` | 底层 LLM backend 参数。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2._init_llm`；`Terminus2.__init__` |
| `agent.kwargs.llm_backend` / `llm_kwargs` / `llm_call_kwargs` | 切换 LiteLLM / Tinker 与调用额外参数。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2._init_llm`；`Terminus2.run` |
| `agent.kwargs.enable_summarize` / `proactive_summarization_threshold` / `interleaved_thinking` / `store_all_messages` | 上下文管理与总结策略。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2.__init__`；`_summarize`；`_run_agent_loop` |
| `agent.kwargs.trajectory_config` | 支持 `raw_content`、`linear_history`。 | `src/harbor/models/agent/trajectory_config.py`；`src/harbor/agents/terminus_2/terminus_2.py::Terminus2.__init__` |
| `agent.kwargs.tmux_pane_width` / `tmux_pane_height` / `record_terminal_session` | 控制 tmux pane 与 asciinema 录制。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2.setup`；`src/harbor/agents/terminus_2/tmux_session.py` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `agent.env.*` | AgentTrack、EagleEye、模型接入等额外变量。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2._init_agenttrack_instrumentation`；`Terminus2.setup` |
| `task.environment.mcp_servers` | 运行时会被拼进提示词。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2.run` |
| `task.environment.skills_dir` | 会扫描成 `<available_skills>` XML。 | `src/harbor/agents/terminus_2/terminus_2.py::Terminus2._build_skills_section` |

## Harbor job YAML 样例
```yaml
# 自托管模型通常要在宿主机准备 API key / base URL。
jobs_dir: jobs/terminus-2
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
  override_cpus: 4
  override_memory_mb: 8192
  env:
    EAGLEEYE_TRACE_ID: ${EAGLEEYE_TRACE_ID}
  kwargs: {}

agents:
  - name: terminus-2
    model_name: openai/gpt-4.1
    override_timeout_sec: 1800
    override_setup_timeout_sec: 120
    max_timeout_sec: 3600
    env:
      USER_ID: ${USER_ID}
      EXPERIMENT_ID: ${EXPERIMENT_ID}
      NAMESPACE: ${NAMESPACE}
      JOB_ID: ${JOB_ID}
      INSTANCE_ID: ${INSTANCE_ID}
    kwargs:
      max_turns: 80
      parser_name: json
      api_base: ${OPENAI_BASE_URL}
      temperature: 0.2
      reasoning_effort: medium
      enable_summarize: true
      proactive_summarization_threshold: 8000
      max_thinking_tokens: 4096
      model_info:
        max_input_tokens: 128000
        max_output_tokens: 8192
      trajectory_config:
        raw_content: false
      linear_history: true
      tmux_pane_width: 180
      tmux_pane_height: 50
      record_terminal_session: true
      interleaved_thinking: false
      store_all_messages: false
      suppress_max_turns_warning: false
      use_responses_api: false
      llm_backend: litellm
      llm_kwargs: {}
      llm_call_kwargs: {}

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/terminus_2/terminus_2.py::Terminus2.setup`：启动 tmux / asciinema。
- `src/harbor/agents/terminus_2/tmux_session.py`：tmux 与录制细节。

### 运行与产物入口
- `src/harbor/agents/terminus_2/terminus_2.py::Terminus2.run`：构造初始 prompt，注入 MCP 与 skills。
- `src/harbor/agents/terminus_2/terminus_2.py::_run_agent_loop`：主循环。
- `src/harbor/agents/terminus_2/terminus_2.py::_dump_trajectory`：ATIF 落盘。

## 对 instance 的依赖要求
- 任务实例至少要有可交互 shell。
- 语言依赖由 task 环境承担。
- 自托管模型必须补全 `model_info`，否则上下文长度无法可靠解析。

## 文档更新时优先关注
- `src/harbor/agents/terminus_2/terminus_2.py`
- `src/harbor/agents/terminus_2/tmux_session.py`
- `src/harbor/models/agent/trajectory_config.py`

## 差异与取舍
### 优点
- ATIF 与终端观测最完整。
- MCP、skills、总结链路都是一等能力。

### 缺点
- 参数面宽，调参复杂。
- 产品行为不等于外部现成 coding agent。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
