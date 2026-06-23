# Gemini CLI Agent

## 定位
适配 Google Gemini CLI，源码在 `src/harbor/agents/installed/gemini_cli.py`。支持 skills、MCP、多模态图片 observation 和 ATIF。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.model_name` | 要求 `provider/model`。 | `src/harbor/agents/installed/gemini_cli.py::GeminiCli.create_run_agent_commands` |
| `agent.kwargs.sandbox` | 映射 `--sandbox`。 | `src/harbor/agents/installed/gemini_cli.py::GeminiCli.CLI_FLAGS` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini API 凭证。 | `src/harbor/agents/installed/gemini_cli.py::GeminiCli.create_run_agent_commands` |
| `GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` / `GOOGLE_GENAI_USE_VERTEXAI` | Vertex AI 路径。 | `src/harbor/agents/installed/gemini_cli.py::GeminiCli.create_run_agent_commands` |
| `task.environment.mcp_servers` / `skills_dir` | 写入 `~/.gemini/settings.json` 并复制 skills。 | `src/harbor/agents/installed/gemini_cli.py::_build_register_mcp_servers_command`；`_build_register_skills_command` |

## Harbor job YAML 样例
```yaml
# 宿主机先导出：GEMINI_API_KEY 或 GOOGLE_API_KEY；Vertex AI 场景还要导出 GOOGLE_*。
jobs_dir: jobs/gemini-cli
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
    GOOGLE_CLOUD_PROJECT: ${GOOGLE_CLOUD_PROJECT}
    GOOGLE_CLOUD_LOCATION: ${GOOGLE_CLOUD_LOCATION}
  kwargs: {}

agents:
  - name: gemini-cli
    model_name: google/gemini-2.5-pro
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env: {}
    kwargs:
      sandbox: true

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
    task_names:
      - describe-image
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/installed/install-gemini-cli.sh.j2`：nvm + npm 安装 Gemini CLI，并开启 experimental skills。

### 运行与产物入口
- `src/harbor/agents/installed/gemini_cli.py::GeminiCli.create_run_agent_commands`：skills、MCP、CLI 启动。
- `src/harbor/agents/installed/gemini_cli.py::populate_context_post_run`：原始轨迹转 ATIF。

## 对 instance 的依赖要求
- 更适合 glibc Linux。
- 图像理解场景更有价值。

## 文档更新时优先关注
- `src/harbor/agents/installed/gemini_cli.py`
- `src/harbor/agents/installed/install-gemini-cli.sh.j2`
- `tests/unit/agents/installed/test_gemini_cli*`

## 差异与取舍
### 优点
- 多模态支持好。
- ATIF 与图片产物都完整。

### 缺点
- musl 兼容信息不足。
- 前置凭证依赖宿主机环境。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
