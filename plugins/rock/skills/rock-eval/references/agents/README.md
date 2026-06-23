
# Harbor Agent 文档总览

这套文档覆盖 `AgentFactory` 当前注册的 20 个 agent 名称，其中 `swe-agent-internal` 是 `swe-agent` 的兼容别名，并把“参数定义、安装脚本、运行命令、产物解析、环境依赖”都映射回具体源码入口。后续只要这些入口发生 diff，就该同步检查文档。

## 文档入口
| 手册 | README |
| --- | --- |
| 通用参数 | [common-parameters.md](./common-parameters.md) |
| 独有参数大全 | [agent-specific-parameters.md](./agent-specific-parameters.md) |

| Agent | README |
| --- | --- |
| `oracle` | [oracle/README.md](./oracle/README.md) |
| `nop` | [nop/README.md](./nop/README.md) |
| `terminus-2` | [terminus-2/README.md](./terminus-2/README.md) |
| `claude-code` | [claude-code/README.md](./claude-code/README.md) |
| `aider` | [aider/README.md](./aider/README.md) |
| `cline-cli` | [cline-cli/README.md](./cline-cli/README.md) |
| `codex` | [codex/README.md](./codex/README.md) |
| `cursor-cli` | [cursor-cli/README.md](./cursor-cli/README.md) |
| `gemini-cli` | [gemini-cli/README.md](./gemini-cli/README.md) |
| `goose` | [goose/README.md](./goose/README.md) |
| `kimi-cli` | [kimi-cli/README.md](./kimi-cli/README.md) |
| `mini-swe-agent` | [mini-swe-agent/README.md](./mini-swe-agent/README.md) |
| `swe-agent` | [swe-agent/README.md](./swe-agent/README.md) |
| `swe-agent-internal` | [swe-agent-internal/README.md](./swe-agent-internal/README.md) |
| `openclaw` | [openclaw/README.md](./openclaw/README.md) |
| `hermes` | [hermes/README.md](./hermes/README.md) |
| `opencode` | [opencode/README.md](./opencode/README.md) |
| `openhands` | [openhands/README.md](./openhands/README.md) |
| `openhands-sdk` | [openhands-sdk/README.md](./openhands-sdk/README.md) |
| `qwen-coder` | [qwen-coder/README.md](./qwen-coder/README.md) |

## 共享 Agent 参数与源码入口
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.name` | agent 名称或自定义 import path 的入口。 | `src/harbor/models/trial/config.py::AgentConfig`；`src/harbor/agents/factory.py::AgentFactory.create_agent_from_config` |
| `agent.model_name` | 模型标识，Harbor 统一透传到 agent 构造函数。 | `src/harbor/models/trial/config.py::AgentConfig`；`src/harbor/agents/factory.py::AgentFactory.create_agent_from_config` |
| `agent.override_timeout_sec` / `override_setup_timeout_sec` / `max_timeout_sec` | 运行、安装、最大超时覆盖。 | `src/harbor/models/trial/config.py::AgentConfig` |
| `agent.kwargs` | agent 构造参数主入口。 | `src/harbor/models/trial/config.py::AgentConfig.kwargs`；对应 agent 类的 `__init__` / `CLI_FLAGS` / `ENV_VARS` |
| `agent.env` | 从 Harbor 注入到单个 agent 的 `extra_env`。installed agent 中优先级高于 `environment.env`。是否参与前置校验取决于 agent 实现。 | `src/harbor/agents/factory.py::AgentFactory.create_agent_from_config`；`src/harbor/agents/installed/base.py::__init__`；`src/harbor/agents/installed/base.py::run` |

## Trial 级环境参数与源码入口
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `environment.type` / `import_path` | 环境后端选择。 | `src/harbor/models/trial/config.py::EnvironmentConfig`；`src/harbor/environments/factory.py::EnvironmentFactory.create_environment_from_config` |
| `force_build` / `delete` | 控制环境构建与回收。 | `src/harbor/models/trial/config.py::EnvironmentConfig`；各环境类 `start()` / `stop()` |
| `override_cpus` / `override_memory_mb` / `override_storage_mb` / `override_gpus` | 覆盖 task 自带资源约束。 | `src/harbor/models/trial/config.py::EnvironmentConfig`；`src/harbor/environments/base.py::_maybe_override_task_env_config` |
| `suppress_override_warnings` | 关闭覆盖资源时的警告。 | `src/harbor/models/trial/config.py::EnvironmentConfig`；`src/harbor/environments/base.py::_maybe_override_task_env_config` |
| `mounts_json` | 底层环境额外挂载。 | `src/harbor/models/trial/config.py::EnvironmentConfig`；具体环境实现的 `__init__` |
| `environment.env` | 持久环境变量，后续所有 `environment.exec()` 都会继承；对 `BaseInstalledAgent`，setup/run 前还会同步进 agent `_extra_env`。 | `src/harbor/models/trial/config.py::EnvironmentConfig.env`；`src/harbor/environments/base.py::_merge_env`；`src/harbor/agents/installed/base.py::_sync_environment_env` |
| `environment.kwargs` | 环境后端自定义参数。 | `src/harbor/models/trial/config.py::EnvironmentConfig.kwargs`；各环境类 `__init__` |
| `oss_deps` | sandbox 依赖预注入。数据集 OSS 连接细节由 rockcli 填充，用户不需要在 job YAML 中配置。 | `src/harbor/models/trial/config.py::EnvironmentConfig`；`src/harbor/environments/base.py::download_file` / `download_dir` |

## task.toml 环境参数与源码入口
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `build_timeout_sec` / `docker_image` | task 环境构建时间与预构建镜像。 | `src/harbor/models/task/config.py::EnvironmentConfig` |
| `cpus` / `memory_mb` / `storage_mb` / `gpus` / `gpu_types` | task 声明的资源需求。 | `src/harbor/models/task/config.py::EnvironmentConfig`；`src/harbor/environments/base.py::_validate_gpu_support` |
| `allow_internet` | 是否允许联网。 | `src/harbor/models/task/config.py::EnvironmentConfig`；`src/harbor/environments/base.py::_validate_internet_config` |
| `mcp_servers` | task 级 MCP 服务描述。 | `src/harbor/models/task/config.py::MCPServerConfig`；agent 内各 `_build_register_mcp_servers_command()` / `_build_mcp_config_*()` |
| `skills_dir` | task 远端 skills 根目录。 | `src/harbor/models/task/config.py::EnvironmentConfig.skills_dir`；各 agent 的 `_build_register_skills_command()` 或 `Terminus2._build_skills_section()` |

## 环境后端 `kwargs` 入口
| 后端 | 额外字段 | 源码入口 |
| --- | --- | --- |
| `docker` | `keep_containers`、`mounts_json` | `src/harbor/environments/docker/docker.py::DockerEnvironment.__init__` |
| `daytona` | `snapshot_template_name`、`network_block_all`、`auto_stop_interval_mins`、`auto_delete_interval_mins` | `src/harbor/environments/daytona.py::DaytonaEnvironment.__init__` |
| `gke` | `cluster_name`、`region`、`namespace`、`registry_location`、`registry_name`、`project_id`、`memory_limit_multiplier`、`cloud_build_machine_type`、`cloud_build_disk_size_gb` | `src/harbor/environments/gke.py::GKEEnvironment.__init__` |
| `modal` | `secrets`、`registry_secret`、`volumes`、`sandbox_timeout_secs`、`sandbox_idle_timeout_secs` | `src/harbor/environments/modal.py::ModalEnvironment.__init__` |
| `rock` | 共享字段 + `kwargs` 透传 | `src/harbor/environments/rock.py::RockEnvironment.__init__` |
| `e2b` | 共享字段 + `kwargs` 透传 | `src/harbor/environments/e2b.py::E2BEnvironment.__init__` |
| `runloop` | 共享字段 + `kwargs` 透传 | `src/harbor/environments/runloop.py::RunloopEnvironment.__init__` |

## 更新文档时优先关注
- `src/harbor/models/trial/config.py`：共享 trial / agent / environment 参数模型。
- `src/harbor/models/task/config.py`：task.toml 环境参数、`mcp_servers`、`skills_dir`。
- `src/harbor/agents/factory.py`：agent 注册清单与 `extra_env` 注入入口。
- `src/harbor/agents/installed/base.py`：`CLI_FLAGS`、`ENV_VARS`、`setup()`、`run()` 的通用行为。
- `src/harbor/environments/factory.py` 与各环境类 `__init__`：trial 级环境 `kwargs` 的真实消费点。
- `examples/configs/*.yaml`：现成样例配置，适合回查默认用法是否漂移。

## 通用 Harbor job YAML 模板
```yaml
# 可以放在 environment.env 的变量会被 trial 环境继承；
# 对 BaseInstalledAgent 还会同步进 agent._extra_env。
# 少数 agent 仍在 Python 侧直接读宿主机 os.environ，详见单 agent 参数表。

jobs_dir: jobs/example
n_attempts: 1
timeout_multiplier: 1.0
agent_setup_timeout_multiplier: 1.0
orchestrator:
  type: local
  n_concurrent_trials: 1
  quiet: false

environment:
  type: docker
  force_build: true
  delete: true
  override_cpus: 4
  override_memory_mb: 8192
  override_storage_mb: 20480
  override_gpus: 0
  suppress_override_warnings: false
  mounts_json: null
  env:
    OPENAI_API_KEY: ${OPENAI_API_KEY}
    OPENAI_BASE_URL: ${OPENAI_BASE_URL}
    RUNTIME_HINT: /workspace
  kwargs: {}
  oss_deps: {}

agents:
  - name: replace-me
    model_name: provider/model
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env:
      # agent.env 只对当前 agent 生效，且优先级高于 environment.env。
      EXTRA_ENV_FOR_AGENT: value
    kwargs:
      replace_me: value

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

建议先从总览确认共享参数与环境边界，再进入单 agent README 看专属参数、凭证入口和完整 job 样例。
