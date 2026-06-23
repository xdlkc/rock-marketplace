# Claude Code Agent

## 定位
适配 `@anthropic-ai/claude-code` CLI，源码在 `src/harbor/agents/installed/claude_code.py`。支持 MCP、skills、会话日志转 ATIF。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 推荐 `anthropic/<model>`；自定义 base URL 时也支持完整模型名。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode.create_run_agent_commands` |
| `agent.kwargs.max_turns` | 映射 `--max-turns`。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode.CLI_FLAGS` |
| `agent.kwargs.reasoning_effort` | 映射 `--effort`，可选 `low|medium|high`。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode.CLI_FLAGS` |
| `agent.kwargs.max_budget_usd` / `fallback_model` / `append_system_prompt` / `allowed_tools` / `disallowed_tools` | 直接映射 Claude Code CLI flag。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode.CLI_FLAGS` |
| `agent.kwargs.max_thinking_tokens` | 通过 `MAX_THINKING_TOKENS` 注入。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode.ENV_VARS` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | 主凭证；可放在 `agent.env` 或 `environment.env`。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode.create_run_agent_commands` |
| `ANTHROPIC_BASE_URL` / `CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | 运行期接入 Anthropic 官方 API 或兼容网关。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode.create_run_agent_commands` |
| `CLAUDE_CODE_USE_BEDROCK` / `AWS_BEARER_TOKEN_BEDROCK` / `AWS_*` / `AWS_REGION` | Bedrock 模式。 | `src/harbor/agents/installed/claude_code.py::ClaudeCode._is_bedrock_mode`；`ClaudeCode.create_run_agent_commands` |
| `task.environment.mcp_servers` / `skills_dir` | 会写到 `$CLAUDE_CONFIG_DIR/.claude.json` 并复制 skills。 | `src/harbor/agents/installed/claude_code.py::_build_register_mcp_servers_command`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
# 凭证可放在 environment.env 共享，也可放在 agent.env 只给当前 agent。
jobs_dir: jobs/claude-code
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
    ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    AWS_REGION: ${AWS_REGION}
  kwargs: {}

agents:
  - name: claude-code
    model_name: anthropic/claude-sonnet-4-5
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env:
      CLAUDE_CODE_USE_BEDROCK: "0"
      ANTHROPIC_BASE_URL: ${ANTHROPIC_BASE_URL}
    kwargs:
      max_turns: 80
      reasoning_effort: high
      max_budget_usd: "8.0"
      fallback_model: anthropic/claude-3-7-sonnet
      append_system_prompt: You are running inside Harbor.
      allowed_tools: Bash,Edit,Read
      disallowed_tools: WebSearch
      max_thinking_tokens: 4096

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-claude-code.sh.j2`：glibc 走官方安装脚本，Alpine 走 npm。
- `src/harbor/agents/installed/claude_code.py::_install_agent_template_path`：安装脚本入口。

### 运行与产物入口
- `src/harbor/agents/installed/claude_code.py::ClaudeCode.create_run_agent_commands`：运行命令与凭证注入。
- `src/harbor/agents/installed/claude_code.py::ClaudeCode.populate_context_post_run`：会话日志转 ATIF。

## 对 instance 的依赖要求
- 依赖 Node / npm 安装能力。
- Alpine 和 glibc 都有兼容分支。
- task 语言依赖仍由实例负责。

## 文档更新时优先关注
- `src/harbor/agents/installed/claude_code.py`
- `src/harbor/agents/installed/install-claude-code.sh.j2`
- `tests/unit/agents/installed/test_claude_code_*`

## 差异与取舍
### 优点
- 产品能力成熟，ATIF 完整。
- MCP 与 skills 支持强。

### 缺点
- Claude Code 自身的产品行为变化需要持续跟进。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
