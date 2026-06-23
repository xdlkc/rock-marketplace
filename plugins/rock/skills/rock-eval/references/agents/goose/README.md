# Goose Agent

## 定位
适配 Block Goose CLI，源码在 `src/harbor/agents/installed/goose.py`。支持 recipe、MCP extension、skills 和 ATIF。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 要求 `provider/model`。 | `src/harbor/agents/installed/goose.py::Goose.create_run_agent_commands` |
| `agent.kwargs.max_turns` | 映射 `--max-turns`。 | `src/harbor/agents/installed/goose.py::Goose.CLI_FLAGS` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `GEMINI_API_KEY` | 常见 provider 凭证。 | `src/harbor/agents/installed/goose.py::Goose.create_run_agent_commands` |
| `DATABRICKS_HOST` / `DATABRICKS_TOKEN` / `TETRATE_API_KEY` / `TETRATE_HOST` | 专用 provider 配置。 | `src/harbor/agents/installed/goose.py::Goose.create_run_agent_commands` |
| `task.environment.mcp_servers` / `skills_dir` | 转成 recipe extensions 与 Goose skills。 | `src/harbor/agents/installed/goose.py::_build_mcp_extensions`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
# 宿主机先导出与 provider 对应的凭证，例如 ANTHROPIC_API_KEY。
jobs_dir: jobs/goose
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
  - name: goose
    model_name: anthropic/claude-3-5-sonnet-20241022
    override_timeout_sec: 1800
    override_setup_timeout_sec: 600
    max_timeout_sec: 3600
    env: {}
    kwargs:
      max_turns: 60

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-goose.sh.j2`：安装 Goose CLI、developer/todo 扩展默认配置。

### 运行与产物入口
- `src/harbor/agents/installed/goose.py::Goose.create_run_agent_commands`：recipe、凭证、CLI 启动。
- `src/harbor/agents/installed/goose.py::populate_context_post_run`：日志转 ATIF。

## 对 instance 的依赖要求
- 系统库比普通 Node CLI 多：`bzip2 libxcb1 libgomp1`。
- task 语言依赖仍由实例负责。

## 文档更新时优先关注
- `src/harbor/agents/installed/goose.py`
- `src/harbor/agents/installed/install-goose.sh.j2`
- `tests/unit/agents/installed/test_goose_mcp.py`

## 差异与取舍
### 优点
- provider 覆盖面广。
- 文本 fallback 恢复能力强。

### 缺点
- 凭证依赖宿主机环境。
- 系统依赖偏多。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
