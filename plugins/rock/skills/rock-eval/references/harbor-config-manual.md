# ROCK Harbor Job 配置手册

这份手册面向通过 `rockcli` / `rc` 提交 ROCK Harbor Job 的用户。读它时不需要看 Harbor 源码，重点是：配置文件怎么写、字段放在哪里、对哪些 trial 生效、哪些参数只属于某个 agent 或 environment 后端。

Harbor Job 配置有两类参数：

- Harbor 通用配置：例如 `n_attempts`、`orchestrator.n_concurrent_trials`、`agents[].override_timeout_sec`、`environment.delete`、`verifier.disable`。这些字段由 Harbor Job / Trial 配置模型直接支持。
- 实现专属配置：例如 `terminus-2` 的 `llm_call_kwargs`、Docker environment 的 `keep_containers`。这些字段只能放在对应的 `kwargs` 下，且只对对应实现生效。

未知字段不要依赖。当前配置读取可能忽略多余 key，也可能在更深层构造 agent/environment 时失败；写配置时应只使用本手册或 agent reference 中列出的字段。

## 先看结论

最小可用配置通常只需要指定数据集、task 和 agent。通过 rockcli 提交 Harbor Job 时，数据集默认走 OSS，OSS bucket、路径、鉴权等连接细节由 rockcli 内置填充；用户侧不要手写这些 OSS 连接参数。

```yaml
# 要运行的数据集。所有展开出来的 trial 都来自这里。
datasets:
  - name: your-dataset-name
    registry:
      split: test
    task_names:
      - example-task-id

# 要运行的 agent 列表。列表里每一项是一个单独 agent 配置。
agents:
  - name: terminus-2
    model_name: hosted_vllm/your-model
```

你给出的那组参数应写成下面这种 YAML。这里假设使用 `terminus-2`，因为 `temperature`、`model_info`、`llm_call_kwargs` 是 `terminus-2` 已验证支持的 agent kwargs；换成其他 agent 前必须看对应 agent 手册。

```yaml
# 这个不是 Harbor JobConfig 字段：不要写 timeout: 7200。
# 如果你想限制 agent 运行时长，写 agents[].override_timeout_sec。

# 每个 task、每个 agent 重复跑 5 次。不会在某一次通过后提前停止。
n_attempts: 5

# 保持全局超时倍率为 1.0；各阶段如果没有单独 multiplier，就使用这个倍率。
timeout_multiplier: 1.0

# 同时运行的 trial 数量上限。1 表示整个 job 串行跑 trial。
orchestrator:
  n_concurrent_trials: 1

agents:
  - # 这里示例为 terminus-2；agent kwargs 是否支持取决于这个 name。
    name: terminus-2

    # 单个 agent 的运行超时，单位秒。只影响这个 agent 展开的 trial。
    override_timeout_sec: 7200

    # 只传给 terminus-2 构造函数，不是 Harbor 全局参数。
    kwargs:
      # terminus-2 采样 temperature。
      temperature: 1.0

      # terminus-2 / LiteLLM 使用的模型能力信息。
      # 这是描述模型上下文和输出能力，不等于单次生成上限。
      model_info:
        max_input_tokens: 262144
        max_output_tokens: 80000

      # 每次 LLM 调用时透传给后端的参数。
      llm_call_kwargs:
        top_p: 0.95
        max_tokens: 16384
        extra_body:
          # provider 专属参数；只有对应后端支持时才会生效。
          top_k: 20

environment:
  # trial 结束时不删除 environment。对排查有用，批量跑时谨慎使用。
  delete: false

  # 只传给具体 environment 后端。keep_containers 是 docker 后端专属参数。
  kwargs:
    keep_containers: true
```

这组参数的适用范围如下：

| 参数 | 是否所有 agent 适用 | 应该写到哪里 | 作用范围 |
| --- | --- | --- | --- |
| `timeout=7200` | 否 | 不应写进 Harbor Job YAML；Harbor JobConfig 没有顶层 `timeout` 字段 | 如果你想控制 agent runtime，用 `agents[].override_timeout_sec`；如果是 rockcli 外层 job 超时，按 rc/平台参数配置，不属于本 YAML |
| `n_attempts=5` | 是 | 顶层 `n_attempts: 5` | 全 job，展开到所有 task 和所有 agent |
| `timeout_multiplier=1.0` | 是 | 顶层 `timeout_multiplier: 1.0` | 所有 trial 的 agent/verifier/setup/environment build 超时倍率，除非对应阶段 multiplier 覆盖 |
| `orchestrator.n_concurrent_trials=1` | 是 | `orchestrator.n_concurrent_trials: 1` | 全 job 的 trial 并发上限 |
| `agents.0.override_timeout_sec=7200` | 是 | 第一个 agent 项下 `override_timeout_sec: 7200` | 只影响 `agents[0]` 展开的 trial |
| `agents.0.kwargs.temperature=1.0` | 否 | `agents[0].kwargs.temperature` | 只传给第一个 agent；是否生效取决于该 agent 是否支持 |
| `agents.0.kwargs.model_info.max_input_tokens=262144` | 否 | `agents[0].kwargs.model_info.max_input_tokens` | `terminus-2`、`openhands` 等支持 `model_info` 的 agent 专属 |
| `agents.0.kwargs.model_info.max_output_tokens=80000` | 否 | `agents[0].kwargs.model_info.max_output_tokens` | 同上；描述模型能力，不是单次生成上限 |
| `agents.0.kwargs.llm_call_kwargs.top_p=0.95` | 否 | `agents[0].kwargs.llm_call_kwargs.top_p` | `terminus-2` 的每次 LLM 调用参数 |
| `agents.0.kwargs.llm_call_kwargs.max_tokens=16384` | 否 | `agents[0].kwargs.llm_call_kwargs.max_tokens` | `terminus-2` 的单次调用生成上限 |
| `agents.0.kwargs.llm_call_kwargs.extra_body.top_k=20` | 否 | `agents[0].kwargs.llm_call_kwargs.extra_body.top_k` | provider 专属后端参数；不是 Harbor 标准字段 |
| `environment.delete=false` | 是 | `environment.delete: false` | 所有 trial 的 environment 清理策略 |
| `environment.kwargs.keep_containers=true` | 否 | `environment.kwargs.keep_containers: true` | Docker environment 专属；其他后端不应假设支持 |

## 哪些配置对所有 agent 生效，哪些只对单个 agent 生效

| 配置位置 | 生效范围 | 典型用途 |
| --- | --- | --- |
| 顶层 `n_attempts` | 全 job。对所有 task、所有 agent 生效 | 重复运行同一组 task/agent |
| 顶层 `timeout_multiplier` | 所有 trial，作为各阶段默认超时倍率 | 整体放大或缩短超时 |
| 顶层 `agent_timeout_multiplier` | 所有 trial 的 agent runtime 阶段 | 只调整 agent 执行超时倍率 |
| 顶层 `verifier_timeout_multiplier` | 所有 trial 的 verifier 阶段 | 只调整 verifier 执行超时倍率 |
| 顶层 `agent_setup_timeout_multiplier` | 所有 trial 的 agent setup 阶段 | 只调整 agent 安装/setup 超时倍率 |
| 顶层 `environment_build_timeout_multiplier` | 所有 trial 的 environment build 阶段 | 只调整环境构建超时倍率 |
| `orchestrator.*` | 全 job 调度层 | 控制 trial 并发、重试、队列行为 |
| `environment.*` | 所有 trial 的环境层 | 选择后端、资源 override、环境变量、清理策略 |
| `verifier.*` | 所有 trial 的评分层 | 是否跳过 verifier、verifier 超时、native/container verifier |
| `metrics[]` | job 聚合结果 | 选择 `mean`、`sum`、`min`、`max`、`uv-script` |
| `agents[]` | 列表中每个 agent 独立生效 | 多模型/多 agent 对比 |
| `agents[].kwargs` | 只传给当前 agent 实现 | agent 专属采样、安装版本、CLI flag |
| `agents[].env` | 只注入当前 agent | 单个 agent 的 token/base URL 等环境变量 |
| `environment.kwargs` | 只传给当前 environment 后端 | Docker/Daytona/GKE/Modal/ROCK 后端专属参数 |

常见混淆：

- `n_attempts` 不是 retry，也不是 pass@k early stop。它只是把每个 `task x agent` 重复展开 N 次。
- `orchestrator.n_concurrent_trials` 是全 job 并发上限，不是“每个 agent 并发数”。
- `agents[].override_timeout_sec` 是单个 agent 的 runtime 超时，单位秒。它不是 setup 超时，也不是 verifier 超时。
- `timeout_multiplier` 会乘到 agent runtime、verifier runtime、agent setup、environment build；某阶段设置了专用 multiplier 时，该阶段用专用值。
- `environment.*` 影响每个 trial 的运行环境；`environment.kwargs` 只属于所选后端，不是全局扩展字段。
- `verifier.*` 影响评分阶段；`verifier.disable: true` 会跳过 verifier，不代表 agent 成功。
- `agents[].kwargs` 不是万能字段。它只进入对应 agent 构造函数，其他 agent 不一定认识。

## 一次 rockcli 提交的 Harbor Job 是怎么展开的

一次 Harbor Job 会先确定 task 列表，再按下面的形态展开：

```text
n_attempts x tasks x agents = trial 列表
```

每个 trial 只有一个 task、一个 agent、一个 environment、一个 verifier。举例：

```yaml
n_attempts: 5
orchestrator:
  n_concurrent_trials: 2
agents:
  - name: terminus-2
    model_name: model-a
  - name: terminus-2
    model_name: model-b
datasets:
  - name: my-dataset
    registry:
      split: test
    task_names: [task-1, task-2]
```

这会生成 `5 x 2 tasks x 2 agents = 20` 个 trial。`n_concurrent_trials: 2` 表示这 20 个 trial 同时最多跑 2 个。

Harbor 会把 `environment`、`verifier`、`artifacts`、timeout multiplier 等全局 trial 配置复制到每个 trial；`agents[]` 列表中的每个 agent 配置会分别进入自己的 trial。

## 常用配置模板

### 单 agent 单模型跑 5 次

```yaml
# 每个 task 用同一个 agent 重复跑 5 次。
n_attempts: 5

# 同时只跑 1 个 trial，便于控制资源和排查。
orchestrator:
  n_concurrent_trials: 1

agents:
  - name: terminus-2
    model_name: hosted_vllm/my-model
    override_timeout_sec: 7200
    kwargs:
      temperature: 1.0

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

### 多 agent 对比

```yaml
# 每个 task 每个 agent 跑 1 次。
n_attempts: 1

# 全 job 同时最多 2 个 trial，不按 agent 分桶。
orchestrator:
  n_concurrent_trials: 2

agents:
  - name: terminus-2
    model_name: hosted_vllm/model-a
    kwargs:
      temperature: 0.7

  - name: terminus-2
    model_name: hosted_vllm/model-b
    kwargs:
      temperature: 1.0

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
      - task-id-2
```

### 指定 task_names

```yaml
datasets:
  - # 数据集名；rockcli 默认按 OSS 数据集处理并填充 registry 细节。
    name: your-dataset

    # 数据集 split。
    registry:
      split: test

    # 只运行这些 task。OSS 数据集需要精确 task name，不支持 glob。
    task_names:
      - astropy__astropy-12907
      - django__django-11099
```

rockcli 提交场景下数据集默认走 OSS，`task_names` 必须显式给出精确 task name，不支持 glob、`exclude_task_names` 或 `n_tasks`。不要在 YAML 里手写 OSS bucket、路径、AccessKey 等连接参数；这些由 rockcli 填充。

### 保留环境/容器便于排查

```yaml
environment:
  # trial 结束后不删除环境资源。适合单任务排查，不适合大批量长跑默认开启。
  delete: false

  # Docker 后端专属：如果 cleanup 被调用且 delete=true，保留并 stop 容器而不是 down 删除。
  # 与 delete=false 一起写时，排查意图更明确；但它不是其他 environment 后端的通用字段。
  kwargs:
    keep_containers: true
```

### 配置 agent LLM 参数

```yaml
agents:
  - name: terminus-2
    model_name: hosted_vllm/my-model
    kwargs:
      # terminus-2 构造参数。
      temperature: 1.0

      # LiteLLM model info。只对支持该字段的 agent 有意义。
      model_info:
        max_input_tokens: 262144
        max_output_tokens: 80000

      # 传给每次 LLM 调用。
      llm_call_kwargs:
        top_p: 0.95
        max_tokens: 16384
        extra_body:
          top_k: 20
```

## 参数总览表

### Job 顶层字段

| 字段 | 类型/示例 | 默认行为 | 生效范围 | 含义 |
| --- | --- | --- | --- | --- |
| `namespace` | string / `team-a` | `null` | 全 job | 资源租户/命名空间标识，也会写入 `NAMESPACE`，供 rockcli/平台侧资源组织使用 |
| `experiment_id` | string / `exp-42` | `null` | 全 job | 实验标识，也会写入 `EXPERIMENT_ID`，供 rockcli/平台侧资源组织使用 |
| `job_name` | string | 当前时间戳 | 全 job | job 输出目录名 |
| `jobs_dir` | path / `jobs` | `jobs` | 全 job | job 输出根目录 |
| `n_attempts` | int / `5` | `1` | 全 job | 每个 task、每个 agent 重复展开的次数 |
| `timeout_multiplier` | float / `1.0` | `1.0` | 所有 trial | 默认超时倍率，作用到 agent/verifier/setup/environment build |
| `agent_timeout_multiplier` | float/null | `null` | 所有 trial | agent runtime 专用倍率；非空时覆盖 `timeout_multiplier` 对 agent runtime 的影响 |
| `verifier_timeout_multiplier` | float/null | `null` | 所有 trial | verifier runtime 专用倍率；非空时覆盖 `timeout_multiplier` 对 verifier 的影响 |
| `agent_setup_timeout_multiplier` | float/null | `null` | 所有 trial | agent setup 专用倍率；非空时覆盖 `timeout_multiplier` 对 setup 的影响 |
| `environment_build_timeout_multiplier` | float/null | `null` | 所有 trial | environment build 专用倍率；非空时覆盖 `timeout_multiplier` 对环境构建的影响 |
| `debug` | bool / `false` | `false` | 全 job | 打开更详细的 debug 日志 |
| `orchestrator` | object | local orchestrator | 全 job | trial 调度和重试配置 |
| `environment` | object | docker environment | 所有 trial | 运行环境后端、资源、环境变量、清理策略 |
| `verifier` | object | 使用 task 默认 verifier | 所有 trial | 评分器行为和 verifier 超时 |
| `metrics` | list | 空列表 | job 结果聚合 | 配置结果聚合指标 |
| `agents` | list | 默认 `oracle` | 展开为多个 agent trial | 要运行的 agent 列表 |
| `datasets` | list | 空列表 | task 来源 | 从数据集展开 task |
| `artifacts` | list | 空列表 | 每个 trial | trial 结束后额外收集文件/目录 |
| `labels` | map | `{}` | job 元数据 | 给 job 打标签，便于组织和筛选 |

### Orchestrator 字段

| 字段 | 类型/示例 | 默认行为 | 生效范围 | 含义 |
| --- | --- | --- | --- | --- |
| `orchestrator.type` | `local` / `queue` | `local` | 全 job | 调度器类型 |
| `orchestrator.n_concurrent_trials` | int / `1` | `4` | 全 job | 同时运行的 trial 数量上限 |
| `orchestrator.quiet` | bool / `false` | `false` | 全 job | 是否隐藏 trial 进度输出 |
| `orchestrator.retry.max_retries` | int / `0` | `0` | 异常 retry | trial 抛异常后的最大重试次数 |
| `orchestrator.retry.include_exceptions` | list/null | `null` | 异常 retry | 只重试这些异常；`null` 表示除排除列表外都可重试 |
| `orchestrator.retry.exclude_exceptions` | list | timeout/reward 解析等异常 | 异常 retry | 不重试这些异常，优先级高于 include |
| `orchestrator.retry.wait_multiplier` | float / `1.0` | `1.0` | 异常 retry | 指数退避等待倍率 |
| `orchestrator.retry.min_wait_sec` | float / `1.0` | `1.0` | 异常 retry | 重试前最短等待秒数 |
| `orchestrator.retry.max_wait_sec` | float / `60.0` | `60.0` | 异常 retry | 重试前最长等待秒数 |
| `orchestrator.kwargs` | map | `{}` | 所选 orchestrator | 传给调度器实现的专属参数 |

`orchestrator.retry` 只处理 trial 执行时抛出的异常。agent 正常结束但 verifier 给 `reward=0` 不会触发这里的 retry。

### Agent 字段

| 字段 | 类型/示例 | 默认行为 | 生效范围 | 含义 |
| --- | --- | --- | --- | --- |
| `agents[].name` | string / `terminus-2` | 未指定 name/import_path 时为 `oracle` | 单个 agent | 内置 agent 名 |
| `agents[].import_path` | `module.path:ClassName` | `null` | 单个 agent | 自定义 agent 类路径；使用它时通常不再设置 `name` |
| `agents[].model_name` | string/null | `null` | 单个 agent | 传给该 agent 的模型名 |
| `agents[].override_timeout_sec` | float/null | task 默认 agent timeout | 单个 agent | 覆盖 agent runtime 超时，单位秒 |
| `agents[].override_setup_timeout_sec` | float/null | Harbor 默认 setup timeout | 单个 agent | 覆盖 agent setup 超时，单位秒 |
| `agents[].max_timeout_sec` | float/null | 无上限 | 单个 agent | agent runtime 超时上限，最终 runtime timeout 会先取 min 再乘倍率 |
| `agents[].kwargs` | map | `{}` | 单个 agent | 传给该 agent 实现的专属参数 |
| `agents[].env` | map string->string | `{}` | 单个 agent | 注入该 agent setup/run 的环境变量，优先级高于 `environment.env` |

### Environment 字段

| 字段 | 类型/示例 | 默认行为 | 生效范围 | 含义 |
| --- | --- | --- | --- | --- |
| `environment.type` | `docker` / `rock` / `daytona` / `gke` / `modal` / `e2b` / `runloop` | `docker` | 所有 trial | 选择 environment 后端 |
| `environment.import_path` | `module.path:ClassName` | `null` | 所有 trial | 自定义 environment 类路径；使用它时通常不再设置 `type` |
| `environment.force_build` | bool / `false` | `false` | 所有 trial | 强制重建环境，即使已有缓存 |
| `environment.delete` | bool / `true` | `true` | 所有 trial | trial 结束后是否清理环境资源 |
| `environment.override_cpus` | int/null | 使用 task 默认 | 所有 trial | 覆盖 task 声明的 CPU 数 |
| `environment.override_memory_mb` | int/null | 使用 task 默认 | 所有 trial | 覆盖 task 声明的内存，单位 MB |
| `environment.override_storage_mb` | int/null | 使用 task 默认 | 所有 trial | 覆盖 task 声明的存储，单位 MB |
| `environment.override_gpus` | int/null | 使用 task 默认 | 所有 trial | 覆盖 task 声明的 GPU 数 |
| `environment.suppress_override_warnings` | bool / `false` | `false` | 所有 trial | 关闭资源 override 警告 |
| `environment.mounts_json` | list/null | `null` | 支持挂载的 environment | 额外挂载配置 |
| `environment.env` | map string->string | `{}` | 所有 trial 环境 | 注入 environment 持久环境变量；installed agent setup/run 前也会同步，但 agent 侧前置校验是否读取取决于具体实现 |
| `environment.kwargs` | map | `{}` | 所选 environment 后端 | 后端专属参数，例如 Docker `keep_containers` |
| `environment.oss_deps` | map | `{}` | 所有 trial | 依赖名/容器路径到 OSS 位置的映射 |
| `environment.tracking` | object/null | `null` | 所有 trial | 实验追踪配置 |
| `environment.tracking.enabled` | bool / `true` | `true` | 所有 trial | 创建 tracking 配置时是否启用 tracker 初始化 |
| `environment.tracking.api_key` | string/null | `ROCK_API_KEY` 回退 | 所有 trial | tracker API key |
| `environment.tracking.params` | map | `{}` | 所有 trial | 合并进 tracker init config 的自定义参数 |

### Verifier 字段

| 字段 | 类型/示例 | 默认行为 | 生效范围 | 含义 |
| --- | --- | --- | --- | --- |
| `verifier.override_timeout_sec` | float/null | task 默认 verifier timeout | 所有 trial | 覆盖 verifier runtime 超时，单位秒 |
| `verifier.max_timeout_sec` | float/null | 无上限 | 所有 trial | verifier runtime 超时上限，最终 timeout 会先取 min 再乘倍率 |
| `verifier.disable` | bool / `false` | `false` | 所有 trial | 是否跳过 verifier |
| `verifier.mode` | `harbor` / `native` / null | 使用 task/default 行为 | 所有 trial | verifier 模式 |
| `verifier.native_config.image` | string/null | `null` | native/container verifier | native/container verifier 使用的镜像 |
| `verifier.native_config.script` | string/null | `null` | native/container verifier | native/container verifier 使用的脚本内容或命令 |
| `verifier.native_config.oss_deps` | map | `{}` | native verifier | native verifier 的 OSS 依赖映射 |
| `verifier.native_config.template.name` | string | 无默认可用值 | native template | Agent-Hub 模板解析 key |
| `verifier.native_config.template.revision` | string/null | latest | native template | 模板 revision |
| `verifier.patch` | bool / `false` | `false` | 所有 trial | verifier 前导出模型 patch artifact |

### Dataset、Task、Metric、Artifact 字段

| 字段 | 类型/示例 | 默认行为 | 生效范围 | 含义 |
| --- | --- | --- | --- | --- |
| `datasets[].name` | string | 必填 | dataset 项 | OSS 数据集名；rockcli 会填充 OSS registry 连接细节 |
| `datasets[].registry.split` | string/null | `null` | dataset 项 | 数据集 split，例如 `test` |
| `datasets[].registry.revision` | string/null | `null` | dataset 项 | 数据集 revision；不需要时留空 |
| `datasets[].task_names` | list | 建议显式填写 | dataset 项 | 只运行这些 task；OSS 数据集需要精确 task name |
| `metrics[].type` | `mean` / `sum` / `min` / `max` / `uv-script` | `mean` | job 聚合 | 聚合类型 |
| `metrics[].kwargs` | map | `{}` | metric 实现 | 传给 metric 构造函数的专属参数 |
| `artifacts[]` | string 或 object | 空列表 | 每个 trial | 额外收集 artifact |
| `artifacts[].source` | string | artifact object 必填 | 每个 trial | artifact 源路径 |
| `artifacts[].destination` | string/null | 默认目标名 | 每个 trial | artifact 收集后的目标路径/名称 |

## 完整带中文注释 YAML

下面是一个覆盖常用字段的完整样例。不要把它原样用于生产，按需要删减。

```yaml
# 可选：资源租户或团队标识。会写入 NAMESPACE，供平台侧资源组织使用。
namespace: my-team

# 可选：实验标识。会写入 EXPERIMENT_ID，供平台侧资源组织使用。
experiment_id: exp-2026-06-23

# job 输出目录名。为空时 Harbor 会用当前时间生成。
job_name: my-harbor-job

# job 输出根目录。
jobs_dir: jobs

# 每个 task、每个 agent 重复运行次数。
n_attempts: 5

# 默认超时倍率。没有设置阶段专用倍率时，各阶段都乘这个值。
timeout_multiplier: 1.0

# agent runtime 阶段专用倍率。null 表示使用 timeout_multiplier。
agent_timeout_multiplier: null

# verifier runtime 阶段专用倍率。null 表示使用 timeout_multiplier。
verifier_timeout_multiplier: null

# agent setup 阶段专用倍率。null 表示使用 timeout_multiplier。
agent_setup_timeout_multiplier: null

# environment build 阶段专用倍率。null 表示使用 timeout_multiplier。
environment_build_timeout_multiplier: null

# 是否启用 debug 日志。
debug: false

# trial 调度配置。
orchestrator:
  # 调度器类型。常用 local；queue 用于队列调度。
  type: local

  # 同时运行的 trial 数量上限。
  n_concurrent_trials: 1

  # 是否隐藏 trial 进度输出。
  quiet: false

  # trial 抛异常时的 retry 策略。
  retry:
    # 初次失败后的最大重试次数。0 表示不重试。
    max_retries: 0

    # 只重试这些异常。null 表示除 exclude_exceptions 外都可重试。
    include_exceptions: null

    # 不重试这些异常。优先级高于 include_exceptions。
    exclude_exceptions:
      - AgentTimeoutError
      - VerifierTimeoutError
      - RewardFileNotFoundError
      - RewardFileEmptyError
      - VerifierOutputParseError

    # 指数退避等待倍率。
    wait_multiplier: 1.0

    # 重试前最短等待秒数。
    min_wait_sec: 1.0

    # 重试前最长等待秒数。
    max_wait_sec: 60.0

  # 调度器专属参数。local 通常不需要；queue 可按队列实现要求填写。
  kwargs: {}

# 所有 trial 共用的 environment 配置。
environment:
  # environment 后端。可选 docker、rock、daytona、gke、modal、e2b、runloop。
  type: docker

  # 自定义 environment 类路径；使用它时通常不再设置 type。
  import_path: null

  # 是否强制重建环境。
  force_build: false

  # trial 结束后是否清理环境资源。排查时可设 false。
  delete: false

  # 覆盖 task 声明的 CPU 数。null 表示使用 task 默认。
  override_cpus: null

  # 覆盖 task 声明的内存，单位 MB。null 表示使用 task 默认。
  override_memory_mb: null

  # 覆盖 task 声明的存储，单位 MB。null 表示使用 task 默认。
  override_storage_mb: null

  # 覆盖 task 声明的 GPU 数。null 表示使用 task 默认。
  override_gpus: null

  # 是否关闭资源 override warning。
  suppress_override_warnings: false

  # 额外挂载配置。仅支持该能力的后端会消费。
  mounts_json: null

  # 注入所有 trial 环境的环境变量。agent.env 可对单 agent 覆盖。
  env: {}

  # environment 后端专属参数。下面 keep_containers 只适用于 docker。
  kwargs:
    keep_containers: true

  # trial 运行前要准备的 OSS 依赖映射。
  oss_deps: {}

  # 实验追踪配置。null 表示不启用。
  tracking: null

# 所有 trial 共用的 verifier 配置。
verifier:
  # 覆盖 verifier 运行超时，单位秒。null 表示使用 task 默认。
  override_timeout_sec: null

  # verifier 超时上限，单位秒。null 表示无额外上限。
  max_timeout_sec: null

  # 是否跳过 verifier。true 会跳过评分，不代表 agent 成功。
  disable: false

  # verifier 模式。null 表示使用 task/default 行为。
  mode: null

  # native/container verifier 配置。
  native_config:
    # container verifier 镜像。null 表示不指定。
    image: null
    # container verifier 脚本内容或命令。null 表示不指定。
    script: null
    # native verifier 需要的 OSS 依赖。
    oss_deps: {}
    # Agent-Hub 模板解析配置。普通 Harbor Job 不需要。
    template: null

  # 是否在 verifier 前导出模型 patch artifact。
  patch: false

# job 级结果聚合指标。
metrics:
  - # 聚合类型：mean、sum、min、max、uv-script。
    type: mean
    # metric 实现专属参数。
    kwargs: {}

# 要运行的 agent 列表。每一项只影响该 agent 展开的 trial。
agents:
  - # 内置 agent 名。
    name: terminus-2

    # 自定义 agent 类路径；使用它时通常不设置 name。
    import_path: null

    # 模型名。具体格式取决于 agent。
    model_name: hosted_vllm/my-model

    # agent runtime 超时，单位秒。只影响这个 agent。
    override_timeout_sec: 7200

    # agent setup 超时，单位秒。null 表示使用 Harbor 默认 setup 超时。
    override_setup_timeout_sec: null

    # agent runtime 超时上限。null 表示无额外上限。
    max_timeout_sec: null

    # agent 专属参数。这里示例为 terminus-2。
    kwargs:
      temperature: 1.0
      model_info:
        max_input_tokens: 262144
        max_output_tokens: 80000
      llm_call_kwargs:
        top_p: 0.95
        max_tokens: 16384
        extra_body:
          top_k: 20

    # 只给这个 agent 的环境变量。
    env: {}

# 从 OSS dataset 展开 task。rockcli 会填充 OSS registry 连接细节。
datasets:
  - # 数据集名。
    name: your-dataset
    # 只包含这些 task。OSS 数据集必须精确列出 task name。
    task_names:
      - task-id-1
    # registry 只需要 split/revision 这类数据集选择信息；OSS 连接参数由 rockcli 填充。
    registry:
      # split，例如 test。
      split: test
      # revision。null 表示使用默认 revision。
      revision: null

# 每个 trial 结束后额外收集的 artifact。
artifacts:
  - # artifact 源路径。
    source: /logs/agent/custom-output.txt
    # artifact 目标名。null 表示使用默认目标。
    destination: custom-output.txt

# job 标签，用于组织和筛选。
labels:
  purpose: debug
```

## Agent 专属参数入口

先读通用参数，再读具体 agent。不同 agent 支持的 `kwargs` 不同；不要把一个 agent 的 kwargs 复制到另一个 agent 上后假设会生效。

| 文档 | 用途 |
| --- | --- |
| [references/agents/README.md](./agents/README.md) | Agent 文档总入口，列出所有 agent 手册和配置边界 |
| [references/agents/common-parameters.md](./agents/common-parameters.md) | 所有 agent 共享的 `AgentConfig` 字段、`agent.env` / `environment.env` 优先级、installed-agent 通用 kwargs |
| [references/agents/agent-specific-parameters.md](./agents/agent-specific-parameters.md) | 按 agent 汇总全部专属 `agents[].kwargs`、模型格式、环境变量和兼容别名 |

单 agent 配置手册：

| Agent | 配置手册 |
| --- | --- |
| `oracle` | [references/agents/oracle/README.md](./agents/oracle/README.md) |
| `nop` | [references/agents/nop/README.md](./agents/nop/README.md) |
| `terminus-2` | [references/agents/terminus-2/README.md](./agents/terminus-2/README.md) |
| `claude-code` | [references/agents/claude-code/README.md](./agents/claude-code/README.md) |
| `aider` | [references/agents/aider/README.md](./agents/aider/README.md) |
| `cline-cli` | [references/agents/cline-cli/README.md](./agents/cline-cli/README.md) |
| `codex` | [references/agents/codex/README.md](./agents/codex/README.md) |
| `cursor-cli` | [references/agents/cursor-cli/README.md](./agents/cursor-cli/README.md) |
| `gemini-cli` | [references/agents/gemini-cli/README.md](./agents/gemini-cli/README.md) |
| `goose` | [references/agents/goose/README.md](./agents/goose/README.md) |
| `hermes` | [references/agents/hermes/README.md](./agents/hermes/README.md) |
| `kimi-cli` | [references/agents/kimi-cli/README.md](./agents/kimi-cli/README.md) |
| `mini-swe-agent` | [references/agents/mini-swe-agent/README.md](./agents/mini-swe-agent/README.md) |
| `swe-agent` | [references/agents/swe-agent/README.md](./agents/swe-agent/README.md) |
| `swe-agent-internal` | [references/agents/swe-agent-internal/README.md](./agents/swe-agent-internal/README.md) |
| `openclaw` | [references/agents/openclaw/README.md](./agents/openclaw/README.md) |
| `opencode` | [references/agents/opencode/README.md](./agents/opencode/README.md) |
| `openhands` | [references/agents/openhands/README.md](./agents/openhands/README.md) |
| `openhands-sdk` | [references/agents/openhands-sdk/README.md](./agents/openhands-sdk/README.md) |
| `qwen-coder` | [references/agents/qwen-coder/README.md](./agents/qwen-coder/README.md) |

## kwargs 规则

`kwargs` 是最容易写错的部分。它不是全局万能字段，而是按位置传给不同实现：

| 位置 | 传给谁 | 适用范围 |
| --- | --- | --- |
| `agents[].kwargs` | 当前 agent 构造函数 | 单个 agent 专属 |
| `environment.kwargs` | 当前 environment 后端构造函数 | 某个 environment 后端专属 |
| `orchestrator.kwargs` | 当前 orchestrator 构造函数 | 调度器专属 |
| `metrics[].kwargs` | 当前 metric 构造函数 | metric 专属 |

已有一等字段不要重复塞进 `kwargs`：

```yaml
# 正确：model_name 是 agent 一等字段。
agents:
  - name: terminus-2
    model_name: hosted_vllm/my-model

# 错误：不要把一等字段塞到 agent kwargs。
agents:
  - name: terminus-2
    kwargs:
      model_name: hosted_vllm/my-model
```

```yaml
# 正确：agent runtime 超时是一等字段。
agents:
  - name: terminus-2
    override_timeout_sec: 7200

# 错误：timeout 不是通用 agent kwargs；不同 agent 即使有 timeout kwargs，含义也可能不同。
agents:
  - name: terminus-2
    kwargs:
      timeout: 7200
```

```yaml
# 正确：资源 override 是 environment 一等字段。
environment:
  override_cpus: 8
  override_memory_mb: 32768

# 错误：不要把资源 override 放到 environment.kwargs。
environment:
  kwargs:
    override_cpus: 8
    override_memory_mb: 32768
```

```yaml
# 正确：Docker 后端专属参数放在 environment.kwargs。
environment:
  type: docker
  kwargs:
    keep_containers: true

# 错误：keep_containers 不是顶层 environment 一等字段。
environment:
  keep_containers: true
```

## Environment kwargs

`environment.kwargs` 在一等字段映射之后传给所选 environment 后端。只写当前后端支持的字段。

| environment type | 支持的 kwargs | 说明 |
| --- | --- | --- |
| `docker` | `keep_containers` | Docker 专属；保留/停止容器，便于本地排查 |
| `daytona` | `snapshot_template_name`、`network_block_all`、`auto_stop_interval_mins`、`auto_delete_interval_mins`、`dind_image`、`dind_snapshot` | Daytona 和 Daytona DinD compose 模式专属 |
| `gke` | `cluster_name`、`region`、`namespace`、`registry_location`、`registry_name`、`project_id`、`memory_limit_multiplier`、`cloud_build_machine_type`、`cloud_build_disk_size_gb` | GKE/Kubernetes 专属 |
| `modal` | `secrets`、`registry_secret`、`volumes`、`sandbox_timeout_secs`、`sandbox_idle_timeout_secs` | Modal sandbox 专属 |
| `rock` | `rock_sandbox_config` | 传给 ROCK SandboxConfig 的参数 |
| `e2b` | 无 Harbor 专属字段 | 仅通用 BaseEnvironment wiring |
| `runloop` | 无 Harbor 专属字段 | 仅通用 BaseEnvironment wiring |

普通用户写 config 不需要启动 sandbox 才能确认字段。只有当需要确认更细的 Harbor 运行行为、文件路径或实际配置展开结果时，使用该 skill 的 agent 可以启动一个临时 sandbox 查看：

```bash
rockcli sandbox start \
  --cluster vpc-sg-a \
  --image rock-instances-registry-vpc.cn-shanghai.cr.aliyuncs.com/instance/harbor:8e50674fc2 \
  --wait-for-alive

# 查看完成后必须停止/销毁该 sandbox，避免遗留资源。
rockcli sandbox <sandbox_id> stop
```

这只是排查手段，不是普通 Harbor Job config 的必填步骤；不要为了写 YAML 默认创建 sandbox。

## Verifier 配置

常用写法：

```yaml
verifier:
  # 使用 task 默认 verifier，且不跳过评分。
  disable: false

  # 覆盖 verifier 运行超时，单位秒。
  override_timeout_sec: 1800
```

native/container verifier 示例：

```yaml
verifier:
  # 选择 native verifier。
  mode: native

  # verifier 运行超时，单位秒。
  override_timeout_sec: 1800

  native_config:
    # container verifier 使用的镜像。
    image: python:3.12

    # container verifier 使用的脚本内容或命令。
    script: /workspace/tests/test.sh

    # native verifier 需要的 OSS 依赖。
    oss_deps: {}
```

`verifier.patch: true` 会在 verifier 前导出模型 patch artifact。它不是“提交代码”或“修改 git 历史”，而是为结果收集 patch 文件。

## 常见问题/排错

### `timeout=7200` 应该写在哪里？

不要写顶层 `timeout: 7200`。Harbor Job YAML 没有这个一等字段。

- 想控制 agent 执行阶段：写 `agents[].override_timeout_sec: 7200`。
- 想控制 verifier 执行阶段：写 `verifier.override_timeout_sec: 7200`。
- 想整体放大 task 默认超时：写 `timeout_multiplier` 或阶段专用 multiplier。
- 如果你说的是 rockcli/平台外层 job 超时，那不属于 Harbor JobConfig YAML。

### `n_attempts: 5` 会不会某次通过后提前停？

不会。它会展开成 5 次 trial。Harbor core 目前没有“某个 task 有一次通过就停止剩余 attempt”的 JobConfig 字段。需要 pass@k 或 early stop 时，应在后处理、metric、adapter 或外层调度里实现。

### `orchestrator.retry.max_retries` 和 `n_attempts` 有什么区别？

`n_attempts` 是计划内重复运行，会生成更多 trial。`orchestrator.retry.max_retries` 是 trial 抛异常后的重试策略，默认不重试 verifier reward 缺失、超时、解析失败等排除列表里的异常；`reward=0` 也不会触发 retry。

### `environment.env` 和 `agents[].env` 谁优先？

`environment.env` 是所有 trial environment 的持久环境变量。对 installed agent，setup/run 前会同步到 agent 运行环境。`agents[].env` 只对当前 agent 生效，并且优先级更高。

少数 agent 会在 Python 侧前置校验时直接读宿主机环境，不一定读取 `environment.env`。遇到凭证/模型环境变量问题时，先看对应 agent reference。

### `environment.delete: false` 和 `environment.kwargs.keep_containers: true` 有什么区别？

`environment.delete: false` 是 Harbor 通用清理开关，表示 trial 结束时不删除环境资源。

`environment.kwargs.keep_containers: true` 是 Docker 后端专属参数。Docker cleanup 被调用且 `delete=true` 时，它会保留并 stop 容器，而不是 `docker compose down` 删除容器。其他后端不要假设支持这个字段。

### LLM 参数没生效怎么办？

先确认它是不是当前 agent 支持的 `kwargs`。例如 `terminus-2` 支持 `temperature`、`model_info`、`llm_call_kwargs`；但同样字段不一定适用于 `claude-code`、`codex`、`swe-agent`。

### 文档里没有的参数能不能写？

不要写。除非你确认它来自 Harbor 配置模型、当前 agent 实现或当前 environment 后端实现。对于未知字段，最常见结果是被忽略、构造时报错，或只在某个 agent 上有不同含义。
