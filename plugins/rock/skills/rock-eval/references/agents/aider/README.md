# Aider Agent

## 定位
适配 `aider.chat` scripting mode，源码在 `src/harbor/agents/installed/aider.py`。实现很薄，主要负责 CLI 参数和凭证拼装。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 必须是 `openai/<model>` 或 `anthropic/<model>`。 | `src/harbor/agents/installed/aider.py::Aider.create_run_agent_commands` |
| `agent.kwargs.reasoning_effort` / `thinking_tokens` / `cache_prompts` / `auto_lint` / `auto_test` / `test_cmd` / `stream` / `map_tokens` | 全部直连 aider CLI。 | `src/harbor/agents/installed/aider.py::Aider.CLI_FLAGS` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | provider 凭证，只读宿主机环境。 | `src/harbor/agents/installed/aider.py::Aider.create_run_agent_commands` |

## Harbor job YAML 样例
```yaml
# 宿主机先导出：OPENAI_API_KEY 或 ANTHROPIC_API_KEY。
jobs_dir: jobs/aider
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
  - name: aider
    model_name: anthropic/claude-3-5-sonnet-20241022
    override_timeout_sec: 1800
    override_setup_timeout_sec: 300
    max_timeout_sec: 3600
    env: {}
    kwargs:
      reasoning_effort: high
      thinking_tokens: 2048
      cache_prompts: true
      auto_lint: true
      auto_test: true
      test_cmd: pytest -q
      stream: true
      map_tokens: 4096

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-aider.sh.j2`：通过官方 install.sh 安装。

### 运行与产物入口
- `src/harbor/agents/installed/aider.py::Aider.create_run_agent_commands`：CLI 与凭证拼装。

## 对 instance 的依赖要求
- 依赖联网拉 installer。
- task 自己要有测试与构建链路，`auto_test` / `auto_lint` 才有意义。

## 文档更新时优先关注
- `src/harbor/agents/installed/aider.py`
- `src/harbor/agents/installed/install-aider.sh.j2`

## 差异与取舍
### 优点
- 集成简单。
- 适合轻量基线对比。

### 缺点
- provider 支持窄。
- 没有 ATIF。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
