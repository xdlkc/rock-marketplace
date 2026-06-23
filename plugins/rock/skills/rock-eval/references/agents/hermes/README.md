# Hermes Agent

## 定位

`hermes` 适配 Hermes CLI，源码在 `src/harbor/agents/installed/hermes.py`。它会生成 `/tmp/hermes/config.yaml`，支持 Anthropic 与 OpenAI-compatible 两类模型入口，并把 Hermes session 导出为 ATIF。

## 参数

共享字段见 [../common-parameters.md](../common-parameters.md)，全量索引见 [../agent-specific-parameters.md](../agent-specific-parameters.md)。

| 参数 | 说明 |
| --- | --- |
| `agent.model_name` | 必填，格式为 `anthropic/<model>` 或 `openai/<model>`。 |
| `agent.kwargs.toolsets` | 映射 `--toolsets`。 |
| `agent.kwargs.max_turns` | 映射 `--max-turns`，并写入 Hermes config；未设置时 config 默认为 `90`。 |
| `agent.kwargs.max_iterations` | 兼容别名，构造阶段归一化为 `max_turns`，不能与 `max_turns` 同时设置。 |
| `agent.kwargs.version` / `node_version` | installed agent 通用安装模板参数。 |

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_TOKEN` | Anthropic provider 凭证。 |
| `ANTHROPIC_BASE_URL` | Anthropic provider 可选 base URL。 |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | `openai/<model>` 路径必需。 |

## 示例

```yaml
agents:
  - name: hermes
    model_name: anthropic/claude-sonnet-4-5
    env:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    kwargs:
      max_turns: 90
      toolsets: file,search,terminal
```

## 维护入口

- `src/harbor/agents/installed/hermes.py`
- `src/harbor/agents/installed/install-hermes.sh.j2`
- `src/harbor/agents/installed/llm_proxy/start.sh`
