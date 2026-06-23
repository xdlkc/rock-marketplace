# Cline CLI Agent

## 定位
适配 Cline CLI，源码在 `src/harbor/agents/installed/cline/cline.py`。支持 nightly、npm 版本、fork、tarball 四种安装来源。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 必须是 `provider:model-id`。 | `src/harbor/agents/installed/cline/cline.py::ClineCli.create_run_agent_commands` |
| `agent.kwargs.tarball_url` / `github_user` / `commit_hash` / `cline_version` | 安装来源选择。 | `src/harbor/agents/installed/cline/cline.py::__init__`；`ClineCli._template_variables`；`src/harbor/agents/installed/cline/install-cline.sh.j2` |
| `agent.kwargs.thinking` / `reasoning_effort` / `double_check_completion` / `max_consecutive_mistakes` | CLI flag。 | `src/harbor/agents/installed/cline/cline.py::ClineCli.CLI_FLAGS` |
| `agent.kwargs.timeout` / `timeout_sec` / `cline_timeout_sec` / `agent_timeout_sec` | 超时别名会归一化。 | `src/harbor/agents/installed/cline/cline.py::__init__`；`_parse_timeout_seconds` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `API_KEY` | 必填 provider 凭证。 | `src/harbor/agents/installed/cline/cline.py::ClineCli.create_run_agent_commands` |
| `BASE_URL` | `openai` provider 时必填。 | `src/harbor/agents/installed/cline/cline.py::ClineCli.create_run_agent_commands` |
| `GITHUB_TOKEN` / `GH_TOKEN` | 安装私有 fork 或 authenticated clone 时使用。 | `src/harbor/agents/installed/cline/cline.py::_setup_env`；`src/harbor/agents/installed/cline/install-cline.sh.j2` |
| `task.environment.mcp_servers` / `skills_dir` | 会写到 `~/.cline/data/settings/cline_mcp_settings.json` 与 `~/.cline/workflows/`。 | `src/harbor/agents/installed/cline/cline.py::_build_register_mcp_servers_command`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
# 宿主机先导出：API_KEY；provider=openai 时还要导出 BASE_URL。
# 如果装私有 fork，再导出 GITHUB_TOKEN 或 GH_TOKEN。
jobs_dir: jobs/cline-cli
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
  - name: cline-cli
    model_name: openrouter:anthropic/claude-opus-4.5
    override_timeout_sec: 1800
    override_setup_timeout_sec: 1800
    max_timeout_sec: 3600
    env: {}
    kwargs:
      tarball_url: null
      github_user: cline
      commit_hash: main
      cline_version: nightly
      thinking: 2048
      reasoning_effort: high
      double_check_completion: true
      max_consecutive_mistakes: 6
      timeout: 1200
      timeout_sec: 1200
      cline_timeout_sec: 1200
      agent_timeout_sec: 1800

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/cline/install-cline.sh.j2`：安装来源选择、fork build 与 link。

### 运行与产物入口
- `src/harbor/agents/installed/cline/cline.py::ClineCli.create_run_agent_commands`：auth、prompt metadata、CLI 启动。
- `src/harbor/agents/installed/cline/cline.py::create_cleanup_commands`：task history 与 prompt artifact 回收。

## 对 instance 的依赖要求
- 更适合 glibc Linux。
- 需要 Node / npm / git。
- 私有 fork 还需要 GitHub 凭证。

## 文档更新时优先关注
- `src/harbor/agents/installed/cline/cline.py`
- `src/harbor/agents/installed/cline/install-cline.sh.j2`
- `tests/unit/agents/installed/test_cline_*`

## 差异与取舍
### 优点
- 版本与安装来源控制最灵活。
- prompt artifact 落盘细。

### 缺点
- `model_name` 格式独特，容易配错。
- 凭证依赖宿主机环境。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
