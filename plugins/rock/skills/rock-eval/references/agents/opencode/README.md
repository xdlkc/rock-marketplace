# OpenCode Agent

## 定位
适配 `opencode-ai` CLI，源码在 `src/harbor/agents/installed/opencode.py`。通过 `--format=json` 的 JSONL 输出构建 ATIF。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 直接传给 `--model`。 | `src/harbor/agents/installed/opencode.py::OpenCode.create_run_agent_commands` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `AWS_*` / `ANTHROPIC_API_KEY` / `AZURE_*` / `DEEPSEEK_API_KEY` / `GITHUB_TOKEN` / `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `GROQ_API_KEY` / `HF_TOKEN` / `LLAMA_API_KEY` / `MISTRAL_API_KEY` / `OPENAI_API_KEY` / `XAI_API_KEY` / `OPENROUTER_API_KEY` | 按 provider 选择读取。 | `src/harbor/agents/installed/opencode.py::OpenCode.create_run_agent_commands` |
| `task.environment.mcp_servers` / `skills_dir` | 写入 `~/.config/opencode/config.json` 和 skills 目录。 | `src/harbor/agents/installed/opencode.py::_build_register_config_command`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
# 与 model_name 匹配的 provider 凭证可放在 environment.env 共享，也可放在 agent.env 覆盖。
jobs_dir: jobs/opencode
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
  - name: opencode
    model_name: anthropic/claude-3-5-sonnet-20241022
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env: {}
    kwargs: {}

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-opencode.sh.j2`：nvm + npm 安装 `opencode-ai`。

### 运行与产物入口
- `src/harbor/agents/installed/opencode.py::OpenCode.create_run_agent_commands`：config 与 CLI 启动。
- `OpenCode.populate_context_post_run`：JSONL 转 ATIF。

## 对 instance 的依赖要求
- 更适合标准 glibc Linux。
- provider 覆盖广，凭证集合也更复杂。

## 文档更新时优先关注
- `src/harbor/agents/installed/opencode.py`
- `src/harbor/agents/installed/install-opencode.sh.j2`

## 差异与取舍
### 优点
- provider 覆盖广。
- ATIF 完整。

### 缺点
- 凭证面很大。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
