# Harbor Agent 通用参数手册

本文只覆盖所有 agent 共享的配置入口。单个 agent 真正消费的 `kwargs`、凭证变量和 `model_name` 格式见 [agent-specific-parameters.md](./agent-specific-parameters.md)。

## AgentConfig 通用字段

源码入口：`src/harbor/models/trial/config.py::AgentConfig`、`src/harbor/agents/factory.py::AgentFactory.create_agent_from_config`。

| 参数 | 类型 | 默认值 | 作用 |
| --- | --- | --- | --- |
| `agent.name` | `str | null` | 未设置且无 `import_path` 时为 `oracle` | 使用内置 agent 名称创建 agent。当前工厂注册清单见 `AgentFactory._AGENTS`，`swe-agent-internal` 是 `swe-agent` 的兼容别名。 |
| `agent.import_path` | `str | null` | `null` | 使用自定义类，格式为 `module.path:ClassName`。设置后由 `AgentFactory.create_agent_from_import_path` 动态导入。 |
| `agent.model_name` | `str | null` | `null` | 模型标识，会透传给 agent 构造函数。多数 agent 要求非空，格式通常是 `provider/model`；`cline-cli` 例外，要求 `provider:model-id`。 |
| `agent.override_timeout_sec` | `float | null` | `null` | 覆盖 agent 执行阶段超时。 |
| `agent.override_setup_timeout_sec` | `float | null` | `null` | 覆盖 agent 安装/setup 阶段超时。 |
| `agent.max_timeout_sec` | `float | null` | `null` | agent 侧最终超时上限。 |
| `agent.kwargs` | `dict` | `{}` | agent 专属参数主入口。内置 installed agents 会先解析 `CLI_FLAGS` / `ENV_VARS`，剩余参数再进入具体实现。 |
| `agent.env` | `dict[str,str]` | `{}` | 注入给单个 agent 的 `extra_env`。installed agents 通过 `_get_env()` 读取时优先级高于 `environment.env` 和宿主机环境。 |

## `agent.env` 与 `environment.env`

源码入口：`src/harbor/agents/installed/base.py::BaseInstalledAgent._sync_environment_env`、`BaseInstalledAgent.run`。

`environment.env` 不只是容器持久环境变量。对继承 `BaseInstalledAgent` 的 agent，setup 和 run 前都会把 `environment.env` 同步进 agent 的 `_extra_env`。

| 入口 | 生效范围 | 优先级 |
| --- | --- | --- |
| `agent.env` | 单个 agent。适合只给某个 agent 的凭证、base URL、fallback 开关。 | 高于 `environment.env`。 |
| `environment.env` | 当前 trial 环境和该环境内运行的 installed agent。适合多个 agent / verifier / 环境命令共享的变量。 | 低于 `agent.env`，高于宿主机环境读取路径。 |
| 宿主机环境 | Harbor 进程所在机器的 `os.environ`。 | 只在未被配置覆盖时使用。 |

需要注意两点：

- 对使用 `_get_env()`、`ENV_VARS.env_fallback` 或 `resolve_openai_compat_creds()` 的 agent，`environment.env` 可以参与 Python 侧解析、校验和运行命令环境。
- 对少数直接在 `create_run_agent_commands()` 里读 `os.environ` 的 agent，`environment.env` 只保证进入最终 shell 环境，不一定能通过 Python 侧前置校验。遇到这种实现，要优先看对应 agent 的参数表。

## task 环境透传给 agent 的字段

源码入口：`src/harbor/models/task/config.py::EnvironmentConfig`、`src/harbor/agents/base.py::BaseAgent`。

| 参数 | 类型 | 作用 |
| --- | --- | --- |
| `task.environment.mcp_servers` | `list[MCPServerConfig]` | 由支持 MCP 的 agent 注册到各自配置文件、recipe 或提示词中。不是所有 agent 都消费。 |
| `task.environment.skills_dir` | `str | null` | 远端 skills 目录。支持 skills 的 agent 会复制或扫描该目录。 |

## BaseInstalledAgent 通用 kwargs

源码入口：`src/harbor/agents/installed/base.py::BaseInstalledAgent`。

这些字段只适用于继承 `BaseInstalledAgent` 的 agent，不适用于 `oracle`、`nop`、`terminus-2` 等非 installed agent。

| `agent.kwargs` 字段 | 类型 | 作用 |
| --- | --- | --- |
| `version` | `str | null` | 安装脚本模板变量。是否真正用于 pin 版本取决于具体 install 模板。 |
| `node_version` | `str | null` | 安装脚本模板变量。显式设置时渲染成固定 Node 版本；未设置时模板通常回退到容器内 `NODE_VERSION` 或默认值。 |
| `python_version` | `str | null` | 安装脚本模板变量。显式设置优先；未设置时 setup 后可从 `PYTHON_VERSION` 环境变量或 agent 默认值解析。 |
| `prompt_template_path` | `str | null` | 可传入自定义 prompt 模板路径；只有读取该模板的 agent 才有实际效果。 |

## CLI_FLAGS / ENV_VARS 解析规则

installed agent 可以声明两类描述符：

| 描述符 | 行为 |
| --- | --- |
| `CLI_FLAGS` | 从 `agent.kwargs` 中取同名字段，按 `str` / `int` / `bool` / `enum` 校验后渲染为 CLI flag。`bool` 为 true 时只输出 flag 本身。 |
| `ENV_VARS` | 从 `agent.kwargs` 或 `env_fallback` 指定的环境变量取值，校验后写入运行命令的环境变量。`env_fallback` 会通过 `_get_env()` 读取，因此能看到 `agent.env` 和 `environment.env`。 |

`agent.kwargs` 中的 kebab-case 别名只有在具体 agent 显式归一化时才支持。不要默认把 `max-turns` 当成 `max_turns`。

## 配置样例

```yaml
environment:
  type: docker
  env:
    # 对 BaseInstalledAgent：setup/run 前会同步进 agent 的 _extra_env。
    # 适合放多个 agent 或运行阶段共享的凭证与 base URL。
    OPENAI_API_KEY: ${OPENAI_API_KEY}
    OPENAI_BASE_URL: ${OPENAI_BASE_URL}

agents:
  - name: claude-code
    model_name: anthropic/claude-sonnet-4-5
    override_timeout_sec: 1800
    override_setup_timeout_sec: 900
    max_timeout_sec: 3600
    env:
      # 只覆盖这个 agent，优先级高于 environment.env。
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    kwargs:
      max_turns: 80
      reasoning_effort: high
      node_version: "22"
```

## 查参数时的源码顺序

1. `AgentConfig`：确认通用字段是否存在。
2. `AgentFactory`：确认 agent 是否当前注册，以及是否有别名。
3. 具体 agent 的 `__init__`：确认构造参数、别名、默认值和校验。
4. 具体 agent 的 `CLI_FLAGS` / `ENV_VARS`：确认 `kwargs` 到 CLI/env 的映射。
5. `create_run_agent_commands()` / install 模板：确认参数是否真的影响运行命令或安装脚本。
