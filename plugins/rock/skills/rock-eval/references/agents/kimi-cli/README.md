# Kimi CLI Agent

## 定位
适配 Kimi Coding CLI，源码在 `src/harbor/agents/installed/kimi_cli.py`。通过 wire protocol 抓事件，再转 ATIF。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 要求 `provider/model`，支持 `moonshot`、`kimi`、`openai`、`anthropic`、`gemini|google`。 | `src/harbor/agents/installed/kimi_cli.py::_PROVIDER_CONFIG`；`KimiCli.create_run_agent_commands` |
| `agent.kwargs.api_key` / `base_url` | 直接覆盖 provider 默认配置。 | `src/harbor/agents/installed/kimi_cli.py::KimiCli.__init__`；`_build_config_json` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `MOONSHOT_API_KEY` / `KIMI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `GOOGLE_API_KEY` | provider 凭证 fallback。 | `src/harbor/agents/installed/kimi_cli.py::_PROVIDER_CONFIG`；`_resolve_api_key` |
| `task.environment.mcp_servers` / `skills_dir` | 写入 `/tmp/kimi-mcp.json` 和 `~/.kimi/skills`。 | `src/harbor/agents/installed/kimi_cli.py::_build_register_mcp_servers_command`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
jobs_dir: jobs/kimi-cli
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
  - name: kimi-cli
    model_name: kimi/kimi-k2
    override_timeout_sec: 1800
    override_setup_timeout_sec: 600
    max_timeout_sec: 3600
    env:
      KIMI_API_KEY: ${KIMI_API_KEY}
    kwargs:
      api_key: ${KIMI_API_KEY}
      base_url: https://api.kimi.com/coding/v1

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-kimi-cli.sh.j2`：`uv tool install --python 3.13 kimi-cli`。

### 运行与产物入口
- `src/harbor/agents/installed/kimi_cli.py::KimiCli.create_run_agent_commands`：config / wire / MCP / skills。
- `KimiCli.populate_context_post_run`：wire 输出转 ATIF。

## 对 instance 的依赖要求
- 依赖 Python 3.13 / uv。
- 对系统要求比 Node CLI 低。

## 文档更新时优先关注
- `src/harbor/agents/installed/kimi_cli.py`
- `src/harbor/agents/installed/install-kimi-cli.sh.j2`

## 差异与取舍
### 优点
- 凭证注入灵活。
- ATIF 完整。

### 缺点
- 生态较小众。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
