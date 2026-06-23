# Harbor Agent 独有参数大全

本文按 `AgentFactory` 当前注册的 agent 汇总每个 agent 的有效 `agent.kwargs`、模型格式、环境变量和兼容别名。共享字段见 [common-parameters.md](./common-parameters.md)。

环境变量列里写到的变量，未特别说明时都可以放在 `agent.env`。对 `BaseInstalledAgent`，多数也可以放在 `environment.env`，因为 setup/run 前会同步进 agent `_extra_env`；但少数适配器在 Python 侧直接读宿主机 `os.environ` 做前置校验，表中会单独标注。

## 支持清单

当前内置工厂注册 20 个 agent 名称，其中 `swe-agent-internal` 是 `swe-agent` 的兼容别名：

| 名称 | 实现类 | 备注 |
| --- | --- | --- |
| `oracle` | `OracleAgent` | 使用 task 自带 solution。 |
| `nop` | `NopAgent` | 空 agent。 |
| `terminus-2` | `Terminus2` | 当前注册的 Terminus 版本；`terminus` / `terminus-1` 只在枚举中保留，不在 `AgentFactory._AGENTS` 中注册。 |
| `claude-code` | `ClaudeCode` | installed agent。 |
| `aider` | `Aider` | installed agent。 |
| `cline-cli` | `ClineCli` | installed agent，`model_name` 用冒号格式。 |
| `codex` | `Codex` | installed agent。 |
| `cursor-cli` | `CursorCli` | installed agent。 |
| `gemini-cli` | `GeminiCli` | installed agent。 |
| `goose` | `Goose` | installed agent。 |
| `kimi-cli` | `KimiCli` | installed agent。 |
| `mini-swe-agent` | `MiniSweAgent` | installed agent。 |
| `swe-agent` | `SweAgent` | installed agent。 |
| `swe-agent-internal` | `SweAgent` | 兼容别名，工厂直接映射到 `SweAgent` 单一实现。 |
| `openclaw` | `OpenClaw` | installed agent。 |
| `hermes` | `Hermes` | installed agent。 |
| `opencode` | `OpenCode` | installed agent。 |
| `openhands` | `OpenHands` | installed agent。 |
| `openhands-sdk` | `OpenHandsSDK` | installed agent。 |
| `qwen-coder` | `QwenCode` | installed agent。 |

## `oracle`

源码：`src/harbor/agents/oracle.py`。

| 参数 | 说明 |
| --- | --- |
| `agent.kwargs` | 无公开专属字段。`task_dir` / `trial_paths` 由 Harbor 内部传入，不应写在 job YAML。 |
| `agent.env` | 与 `task.config.solution.env` 合并后注入 `solve.sh`。 |
| `agent.model_name` | 可留空，不参与运行。 |

## `nop`

源码：`src/harbor/agents/nop.py`。

| 参数 | 说明 |
| --- | --- |
| `agent.kwargs` | 无公开专属字段。 |
| `agent.model_name` | 可留空，不参与运行。 |

## `terminus-2`

源码：`src/harbor/agents/terminus_2/terminus_2.py`。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `agent.model_name` | 必填 | LLM 模型名。 |
| `max_turns` | `null` | 最大回合数；未设置时内部上限为 `1000000`。 |
| `max_episodes` / `episodes` | `null` | 旧别名，仍兼容但会告警。 |
| `parser_name` | `json` | `json` 或 `xml`，决定响应解析器和提示模板。 |
| `api_base` | `null` | LiteLLM API base。 |
| `temperature` | `0.7` | 采样温度。 |
| `reasoning_effort` | `null` | `none|minimal|low|medium|high|default`。 |
| `collect_rollout_details` | `false` | 收集 token ids / logprobs 等 rollout 细节。 |
| `session_id` | 自动 UUID | LLM session id。 |
| `enable_summarize` | `true` | 启用上下文总结。 |
| `proactive_summarization_threshold` | `8000` | 剩余 token 低于该阈值时主动总结；`0` 可关闭主动总结。 |
| `max_thinking_tokens` | `null` | Anthropic extended thinking token budget。 |
| `model_info` | `null` | 自定义模型 token / cost 信息。 |
| `trajectory_config.raw_content` | `false` | 轨迹中保留原始 LLM 响应。 |
| `trajectory_config.linear_history` | `false` | 上下文总结后拆出线性历史轨迹。 |
| `tmux_pane_width` / `tmux_pane_height` | `160` / `40` | tmux pane 尺寸。 |
| `record_terminal_session` | `true` | 是否录制 asciinema。 |
| `store_all_messages` | `false` | 是否在结果 metadata 中保留完整 chat messages。 |
| `interleaved_thinking` | `false` | 是否把 reasoning 内容写回下一轮上下文。 |
| `suppress_max_turns_warning` | `false` | 关闭 max_turns 限制告警。 |
| `use_responses_api` | `false` | LiteLLM 是否走 Responses API。 |
| `llm_backend` | `litellm` | `litellm` 或 `tinker`。 |
| `llm_kwargs` | `null` | 传给 LLM 构造函数的额外参数。 |
| `llm_call_kwargs` | `null` | 每次 LLM 调用额外参数，例如 `extra_body`。 |

额外入口：`task.environment.mcp_servers` 会拼进提示词；`skills_dir` 会扫描成 `<available_skills>` XML。

## `claude-code`

源码：`src/harbor/agents/installed/claude_code.py`。

| 参数 | 默认值 / 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 可选 | 写入 `ANTHROPIC_MODEL`；Bedrock ARN 可原样传入。 |
| `max_turns` | `int | null` | `--max-turns`；也可从 `CLAUDE_CODE_MAX_TURNS` 回退。 |
| `max_iterations` | alias | 构造阶段归一化为 `max_turns`，不能同时设置。 |
| `reasoning_effort` | `low|medium|high` | `--effort`；也可从 `CLAUDE_CODE_EFFORT_LEVEL` 回退。 |
| `max_budget_usd` | `str` | `--max-budget-usd`。 |
| `fallback_model` | `str` | `--fallback-model`。 |
| `append_system_prompt` | `str` | `--append-system-prompt`。 |
| `allowed_tools` | `str` | `--allowedTools`。 |
| `disallowed_tools` | `str` | `--disallowedTools`。 |
| `max_thinking_tokens` | `int` | `MAX_THINKING_TOKENS`。 |
| `version` / `node_version` | installed 通用 | 安装模板变量。 |

凭证/环境：`ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`、`CLAUDE_CODE_OAUTH_TOKEN`、`CLAUDE_CODE_MAX_OUTPUT_TOKENS`、Bedrock 相关 `AWS_*` / `CLAUDE_CODE_USE_BEDROCK`。这些变量可放在 `agent.env` 或 `environment.env`；最终运行环境会以后者为基础、前者覆盖。支持 `task.environment.mcp_servers` 和 `skills_dir`。

## `aider`

源码：`src/harbor/agents/installed/aider.py`。

| 参数 | 映射 |
| --- | --- |
| `agent.model_name` | 必须为 `openai/<model>` 或 `anthropic/<model>`。 |
| `reasoning_effort` | `--reasoning-effort`。 |
| `thinking_tokens` | `--thinking-tokens`。 |
| `cache_prompts` | `--cache-prompts`。 |
| `auto_lint` | `--auto-lint`。 |
| `auto_test` | `--auto-test`。 |
| `test_cmd` | `--test-cmd`。 |
| `stream` | `--stream`。 |
| `map_tokens` | `--map-tokens`。 |
| `version` / `python_version` | installed 通用。 |

凭证：Python 侧只从宿主机读取 `OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY`，并转成 `AIDER_API_KEY`；不要只放在 `environment.env`，否则会过不了前置读取。

## `cline-cli`

源码：`src/harbor/agents/installed/cline/cline.py`。

| 参数 | 默认值 / 类型 | 说明 |
| --- | --- | --- |
| `agent.model_name` | 必填 | 格式为 `provider:model-id`，不是 `provider/model`。 |
| `tarball_url` / `tarball-url` | `str | null` | 预构建 CLI tarball。 |
| `github_user` / `github-user` | `str | null` | Cline fork owner。 |
| `commit_hash` / `commit-hash` | `main` | 分支、tag 或 commit；仅给 `commit_hash` 时默认 `github_user=cline`。 |
| `cline_version` / `cline-version` | `str | null` | npm 版本。 |
| `thinking` | `int | null` | `--thinking`，必须非负。 |
| `reasoning_effort` / `reasoning-effort` | `none|low|medium|high|xhigh` | `--reasoning-effort`。 |
| `double_check_completion` / `double-check-completion` | `bool | null` | true 时输出 `--double-check-completion`。兼容 `double_check_completions` / `double-check-completions`。 |
| `max_consecutive_mistakes` / `max-consecutive-mistakes` | `int | null` | `--max-consecutive-mistakes`，必须非负。 |
| `timeout` / `timeout_sec` / `timeout-sec` / `timeout-seconds` | `int | null` | CLI `-t` 超时来源。 |
| `cline_timeout_sec` / `cline-timeout-sec` / `cline-timeout` | `int | null` | CLI 超时别名，优先级高于 `timeout_sec` / `timeout`。 |
| `agent_timeout_sec` | `int | null` | Harbor agent 超时值，可作为 Cline 超时 fallback。 |
| `version` / `node_version` | installed 通用 | 安装模板变量。 |

凭证/环境：运行时使用 `API_KEY`；`provider=openai` 还要求 `BASE_URL`。当前 Python 侧直接读宿主机环境；不要只放在 `environment.env`。支持 `task.environment.mcp_servers` 和 `skills_dir`。

## `codex`

源码：`src/harbor/agents/installed/codex.py`。

| 参数 | 默认值 / 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 必填 | CLI 中取最后一段作为 `-m <model>`。 |
| `reasoning_effort` | `high` | `-c model_reasoning_effort=<value>`。 |
| `reasoning_summary` | `auto|concise|detailed|none` | `-c model_reasoning_summary=<value>`。 |
| `version` / `node_version` | installed 通用 | 安装模板变量。 |

凭证/环境：`OPENAI_API_KEY` 可放在 `agent.env` 或 `environment.env`。支持 `task.environment.mcp_servers` 和 `skills_dir`。

## `cursor-cli`

源码：`src/harbor/agents/installed/cursor_cli.py`。

| 参数 | 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 必填 `provider/model` | CLI 中取最后一段作为 `--model=<model>`。 |
| `mode` | `plan|ask|agent` | `--mode`。 |
| `version` / `node_version` | installed 通用 | 安装模板变量。 |

凭证/环境：`CURSOR_API_KEY` 在 Python 侧只从宿主机环境读取；不要只放在 `environment.env`。支持 `task.environment.mcp_servers`。

## `gemini-cli`

源码：`src/harbor/agents/installed/gemini_cli.py`。

| 参数 | 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 可选 | 运行时由 Gemini CLI 处理。 |
| `sandbox` | `bool` | true 时输出 `--sandbox`。 |
| `version` / `node_version` | installed 通用 | 安装模板变量。 |

凭证/环境：通常使用 Gemini CLI 支持的 Google/Gemini 环境变量。该适配器支持 ATIF。

## `goose`

源码：`src/harbor/agents/installed/goose.py`。

| 参数 | 映射 |
| --- | --- |
| `agent.model_name` | 必须为 `provider/model`。支持 `openai`、`anthropic`、`google` / `gemini`。 |
| `max_turns` | `--max-turns`。 |
| `version` / `node_version` | installed 通用；`version` 未设置时显示为 `stable`。 |

凭证/环境：`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY` 或 `GEMINI_API_KEY` 在 Python 侧直接从宿主机读取；不要只放在 `environment.env`。支持 `task.environment.mcp_servers` 和 `skills_dir`。

## `kimi-cli`

源码：`src/harbor/agents/installed/kimi_cli.py`。

| 参数 | 默认值 / 类型 | 说明 |
| --- | --- | --- |
| `agent.model_name` | 必填 `provider/model` | provider 支持 `moonshot`、`kimi`、`openai`、`anthropic`、`gemini`、`google`。 |
| `api_key` | `str | null` | 覆盖 provider 默认凭证查找。 |
| `base_url` | `str | null` | 覆盖 provider 默认 base URL。 |
| `version` / `python_version` | installed 通用 | 默认 Python `3.13`。 |

凭证/环境：按 provider 读取 `MOONSHOT_API_KEY`、`KIMI_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GEMINI_API_KEY`、`GOOGLE_API_KEY`。这些 fallback 在 Python 侧直接读宿主机环境；如果想用配置文件注入，优先用 `agent.kwargs.api_key` / `base_url`。支持 `task.environment.mcp_servers` 和 `skills_dir`。

## `mini-swe-agent`

源码：`src/harbor/agents/installed/mini_swe_agent.py`。

| 参数 | 默认值 / 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 必填 `provider/model` | `--model=<model_name>`。 |
| `cost_limit` | `"0"` | `--cost-limit`。 |
| `reasoning_effort` | `str | null` | 写成 `-c model.model_kwargs.extra_body.reasoning_effort=<value>`。 |
| `config_file` | `str | null` | 读取本地 YAML 文件并写入容器，运行时追加 `-c /tmp/mswea-config/custom.yaml`。 |
| `version` / `python_version` | installed 通用 | 默认 Python `3.12`。 |

凭证/环境：`openai/*` + `OPENAI_API_KEY` / `OPENAI_BASE_URL` 走 OpenAI-compat，支持 `agent.env` 或 `environment.env`；其他 provider key / `MSWEA_API_KEY` 也会从合并后的环境读取。可透传 `OPENAI_API_BASE`。

## `swe-agent` / `swe-agent-internal`

源码：`src/harbor/agents/installed/swe_agent/agent.py`。

| 参数 | 默认值 / 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 必填 | 运行脚本 `MODEL_NAME`。 |
| `per_instance_cost_limit` | `str | null` | `--agent.model.per_instance_cost_limit`。 |
| `total_cost_limit` | `str | null` | `--agent.model.total_cost_limit`。 |
| `max_input_tokens` | `str | null` | `--agent.model.max_input_tokens`。 |
| `temperature` | `str | null` | `--agent.model.temperature`。 |
| `top_p` | `str | null` | `--agent.model.top_p`。 |
| `max_iterations` | `int | null` | `--agent.model.per_instance_call_limit`。 |
| `max_tokens` | `int | null` | `--agent.model.max_output_tokens`。 |
| `num_retries` | `int | null` | `--agent.model.retry.retries`。 |
| `api_key` | `str | null` | `--agent.model.api_key`。 |
| `api_base` | `str | null` | `--agent.model.api_base`。 |
| `tools_parse_function` | `str | null` | `--agent.tools.parse_function.type`。 |
| `max_observation_length` | `int | null` | `--agent.templates.max_observation_length`。 |
| `sweagent_config` | `str | null` | config 名称、绝对路径或 URL；未设置时为 `default`。也可通过 `SWEAGENT_CONFIG` 环境变量。 |
| `completion_kwargs` | `dict | null` | 序列化为 `COMPLETION_KWARGS_JSON` / `--agent.model.completion_kwargs`。 |
| `full_history` | `bool | null` | 序列化为 `FULL_HISTORY` / `--agent.full_history`；OSS fork 能力受安装脚本探测。 |
| `version` / `python_version` | installed 通用 | 默认 Python `3.12`。 |

凭证/环境：`openai/*` + `OPENAI_API_KEY` / `OPENAI_BASE_URL` 走 OpenAI-compat，支持 `agent.env` 或 `environment.env`；否则当前实现主要透传宿主机 `ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`TOGETHER_API_KEY` 或 provider 推断 key。setup 阶段还会透传宿主机 `OSS_*`，供 preprocess 模式使用。

## `openclaw`

源码：`src/harbor/agents/installed/openclaw.py`。

| 参数 | 默认值 / 类型 | 说明 |
| --- | --- | --- |
| `agent.model_name` | 必填 `provider/model` | provider 内置支持 `anthropic`、`google`、`openai`；其他 provider 必须设置 `context_window`，通常还要设置 `<PROVIDER>_BASE_URL`。 |
| `version` | `str | null` | OpenClaw 安装版本。 |
| `context_window` | `int | null` | 模型上下文窗口；非标准 provider 必填，且不能低于 `16384`。 |
| `max_tokens` | `int | null` | 输出 token 上限；有 `context_window` 时写入 inline model 定义，否则写入 `model_params.maxTokens`。 |
| `temperature` | `float | null` | 采样温度；会覆盖 `model_params.temperature`。 |
| `thinking` | `str | null` | 写入 `thinkingDefault`，例如 `off|minimal|low|medium|high|xhigh`。 |
| `model_params` | `dict | null` | 写入 OpenClaw provider model params，例如 `cacheRetention`、`anthropicBeta`。 |
| `node_version` | installed 通用 | 安装模板变量。 |

凭证/环境：按 provider 读取 `<PROVIDER>_API_KEY`，`google` 会读 `GOOGLE_API_KEY`；可用 `<PROVIDER>_BASE_URL` 覆盖 base URL。支持 `agent.env` 或 `environment.env`。

## `hermes`

源码：`src/harbor/agents/installed/hermes.py`。

| 参数 | 默认值 / 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 必填 | 支持 `anthropic/<model>` 或 `openai/<model>`。 |
| `toolsets` | `str | null` | `--toolsets`。 |
| `max_turns` | `int | null` | `--max-turns` 且写入 Hermes config。未设置时 config 默认为 `90`。 |
| `max_iterations` | alias | 构造阶段归一化为 `max_turns`，不能同时设置。 |
| `version` / `node_version` | installed 通用 | 安装模板变量。 |

凭证/环境：Anthropic 路径读取 `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_TOKEN`，可选 `ANTHROPIC_BASE_URL`；OpenAI 路径要求 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。支持 `agent.env` 或 `environment.env`。

## `opencode`

源码：`src/harbor/agents/installed/opencode.py`。

| 参数 | 说明 |
| --- | --- |
| `agent.model_name` | 必填。`openai/<id>` + `OPENAI_BASE_URL` 时会注册内部 `openai-compat` provider，走 chat completions。 |
| `agent.kwargs` | 除 installed 通用字段外，无额外公开专属字段。 |
| `version` / `node_version` | installed 通用。 |

凭证/环境：按 provider / OpenAI-compat 配置写入 `~/.config/opencode/config.json`，支持 `agent.env` 或 `environment.env`。支持 `task.environment.mcp_servers` 和 `skills_dir`。

## `openhands`

源码：`src/harbor/agents/installed/openhands.py`。

| 参数 | 默认值 / 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 可选 | 优先于 `LLM_MODEL` / `ANTHROPIC_MODEL`。 |
| `disable_tool_calls` | `false` | 写入 `LLM_NATIVE_TOOL_CALLING`，true 会写成 `false`。 |
| `reasoning_effort` | `high` | `LLM_REASONING_EFFORT`，可从 `REASONING_EFFORT` 回退。 |
| `temperature` | `str | null` | `LLM_TEMPERATURE`，可从 `TEMPERATURE` 回退。 |
| `max_iterations` | `int | null` | `MAX_ITERATIONS`。 |
| `caching_prompt` | `bool | null` | `LLM_CACHING_PROMPT`。 |
| `top_p` | `str | null` | `LLM_TOP_P`。 |
| `num_retries` | `int | null` | `LLM_NUM_RETRIES`。 |
| `max_budget_per_task` | `str | null` | `MAX_BUDGET_PER_TASK`。 |
| `drop_params` | `bool | null` | `LLM_DROP_PARAMS`。 |
| `disable_vision` | `bool | null` | `LLM_DISABLE_VISION`。 |
| `trajectory_config.raw_content` | `false` | raw completion 轨迹；必须同时 `disable_tool_calls=true`。 |
| `api_base` | `str | null` | OpenHands LLM base URL 辅助字段。 |
| `model_info` | `dict | null` | 自定义模型 token / cost 信息。 |
| `git_version` | `str | null` | 安装模板使用的 Git 版本。 |
| `version` / `python_version` | installed 通用 | 默认 Python `3.13`。 |

凭证/环境：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_VERSION`；`OPENHANDS_*` 会去掉前缀透传给运行时。支持 `agent.env` 或 `environment.env`，也支持 `task.environment.mcp_servers`。

## `openhands-sdk`

源码：`src/harbor/agents/installed/openhands_sdk.py`。

| 参数 | 默认值 / 类型 | 说明 |
| --- | --- | --- |
| `agent.model_name` | 可选 | 优先于 `LLM_MODEL`；二者都缺失会报错。 |
| `reasoning_effort` | `high` | SDK / LLM reasoning effort。 |
| `load_skills` | `true` | 是否加载 skills。 |
| `skill_paths` | 默认内置多目录 | `:` 拼接后写入 `SKILL_PATHS`。 |
| `collect_token_ids` | `false` | true 时写 `LITELLM_EXTRA_BODY={"return_token_ids": true}`。 |
| `max_iterations` | `int | null` | `MAX_ITERATIONS`。 |
| `temperature` | `float | null` | `LLM_TEMPERATURE`。 |
| `version` / `python_version` | installed 通用 | 安装模板变量。 |

凭证/环境：必须有 `LLM_API_KEY`；可选 `LLM_BASE_URL`、`LLM_MODEL`。支持 `agent.env` 或 `environment.env`，也支持 `task.environment.mcp_servers`。

## `qwen-coder`

源码：`src/harbor/agents/installed/qwen_code.py`。

| 参数 | 默认值 / 类型 | 映射 |
| --- | --- | --- |
| `agent.model_name` | 可选 | 设置时写入 `OPENAI_MODEL`，否则回退 `OPENAI_MODEL` 环境变量。 |
| `api_key` | `str | null` | `OPENAI_API_KEY`，可从同名环境变量回退。 |
| `base_url` | `str | null` | `OPENAI_BASE_URL`，可从同名环境变量回退。 |
| `version` / `node_version` | installed 通用 | 安装模板变量。 |

支持 `task.environment.mcp_servers` 和 `skills_dir`。
