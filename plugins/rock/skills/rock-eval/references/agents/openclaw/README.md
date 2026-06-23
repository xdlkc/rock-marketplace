# OpenClaw Agent

## 定位
适配 OpenClaw CLI 本地嵌入模式，源码在 `src/harbor/agents/installed/openclaw.py`。会把 OpenClaw 原生工作区模板写进 `/workspace`。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 要求 `provider/model`。 | `src/harbor/agents/installed/openclaw.py::OpenClaw.create_run_agent_commands` |
| `agent.kwargs.version` | 指定 OpenClaw 版本。 | `src/harbor/agents/installed/openclaw.py::OpenClaw.version`；`_template_variables` |
| `agent.kwargs.context_window` / `max_tokens` / `temperature` / `thinking` / `model_params` | 生成 `~/.openclaw/openclaw.json` 和 provider config。 | `src/harbor/agents/installed/openclaw.py::OpenClaw.__init__`；`_build_provider_config`；`create_run_agent_commands` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `agent.env.<PROVIDER>_API_KEY` / `environment.env.<PROVIDER>_API_KEY` | provider 凭证；`agent.env` 优先于 `environment.env` 和宿主机环境。 | `src/harbor/agents/installed/openclaw.py::_get_api_key_for_provider` |
| `agent.env.<PROVIDER>_BASE_URL` / `environment.env.<PROVIDER>_BASE_URL` | provider base URL override；`agent.env` 优先。 | `src/harbor/agents/installed/openclaw.py::_build_provider_config` |

## Harbor job YAML 样例
```yaml
jobs_dir: jobs/openclaw
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
  - name: openclaw
    model_name: anthropic/claude-opus-4-6
    override_timeout_sec: 1800
    override_setup_timeout_sec: 1200
    max_timeout_sec: 3600
    env:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      ANTHROPIC_BASE_URL: ${ANTHROPIC_BASE_URL}
    kwargs:
      version: null
      context_window: 200000
      max_tokens: 8192
      temperature: 0.2
      thinking: high
      model_params:
        cacheRetention: true

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-openclaw.sh.j2`：Node 22、OpenClaw、workspace 模板和 auth profile。

### 运行与产物入口
- `src/harbor/agents/installed/openclaw.py::OpenClaw.create_run_agent_commands`：config、auth、CLI 启动。
- `OpenClaw.populate_context_post_run`：session JSONL 转 ATIF。

## 对 instance 的依赖要求
- 更适合标准 glibc Linux。
- 未知 provider 必须补 `context_window`。

## 文档更新时优先关注
- `src/harbor/agents/installed/openclaw.py`
- `src/harbor/agents/installed/install-openclaw.sh.j2`
- `src/harbor/agents/installed/openclaw/*.md`

## 差异与取舍
### 优点
- `agent.env` / `environment.env` 支持好。
- 超时后日志恢复能力强。

### 缺点
- 工作区模板侵入性强。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
