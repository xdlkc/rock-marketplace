# Qwen Coder Agent

## 定位
对应实现类 `QwenCode`，源码在 `src/harbor/agents/installed/qwen_code.py`。通过 session JSONL 转 ATIF，并支持 skills / MCP。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.name` | 必须写 `qwen-coder`。 | `src/harbor/models/agent/name.py::AgentName.QWEN_CODE`；`src/harbor/agents/factory.py` |
| `agent.model_name` | 显式给出时写入 `OPENAI_MODEL`；否则回退到合并环境里的 `OPENAI_MODEL`。 | `src/harbor/agents/installed/qwen_code.py::QwenCode.create_run_agent_commands` |
| `agent.kwargs.api_key` / `base_url` | 分别映射 `OPENAI_API_KEY`、`OPENAI_BASE_URL`。 | `src/harbor/agents/installed/qwen_code.py::QwenCode.ENV_VARS` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `agent.env.OPENAI_API_KEY` / `environment.env.OPENAI_API_KEY` / `OPENAI_BASE_URL` | 支持从 `agent.env` 或 `environment.env` 进入解析流程；`agent.env` 优先。 | `src/harbor/agents/installed/qwen_code.py::QwenCode.ENV_VARS`；`create_run_agent_commands` |
| `task.environment.mcp_servers` / `skills_dir` | 会写到 `~/.qwen/settings.json` 与 `~/.qwen/skills`。 | `src/harbor/agents/installed/qwen_code.py::_build_register_mcp_servers_command`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
jobs_dir: jobs/qwen-coder
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
  - name: qwen-coder
    model_name: openai/gpt-5
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL}
    kwargs:
      api_key: ${OPENAI_API_KEY}
      base_url: ${OPENAI_BASE_URL}

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-qwen-code.sh.j2`：nvm + npm 安装 `@qwen-code/qwen-code`。

### 运行与产物入口
- `src/harbor/agents/installed/qwen_code.py::QwenCode.create_run_agent_commands`：skills、MCP、CLI 启动。
- `QwenCode.populate_context_post_run`：session JSONL 转 ATIF。

## 对 instance 的依赖要求
- 更适合标准 glibc Linux。
- `agent.env` / `environment.env` 对凭证支持较好。

## 文档更新时优先关注
- `src/harbor/agents/installed/qwen_code.py`
- `src/harbor/agents/installed/install-qwen-code.sh.j2`
- `tests/unit/agents/installed/test_qwen_code_*`

## 差异与取舍
### 优点
- `agent.env` / `environment.env` 兼容好。
- ATIF 完整。

### 缺点
- provider 抽象不如 OpenCode 宽。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
