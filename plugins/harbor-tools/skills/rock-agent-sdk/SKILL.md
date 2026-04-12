---
name: rock-agent-sdk
description: 辅助开发者基于 ROCK Agent SDK 开发和运行 Agent Benchmark 评测。当用户需要编写 Agent 配置、创建 Job 配置 YAML、使用 rock.sdk.agent API、编写 rock_agent_config.yaml、配置数据集/验证器/编排器、运行 Harbor benchmark 评测、分析评测结果时使用。触发词：agent sdk、rock agent、写 agent 配置、job config、harbor yaml、benchmark 配置、评测配置、rock_agent_config、JobConfig、AgentConfig、VerifierConfig、DatasetConfig、跑 benchmark、agent 开发。即使用户只说"我要跑个 agent 评测"或"帮我写个 harbor 配置"也应触发。
---

# ROCK Agent SDK 开发指南

帮助开发者基于 ROCK Agent SDK（`rock.sdk.agent`）快速编写 Agent 配置、创建 Benchmark 评测 Job、运行并分析结果。

## ROCK 平台背景

**ROCK (Reinforcement Open Construction Kit)** 是阿里巴巴开发的沙箱环境管理框架，专为 Agentic 强化学习场景设计。采用客户端-服务端架构：

| 组件 | 职责 |
|------|------|
| ROCK SDK | 环境开发工具包，提供 Agent 开发、Job 配置、Benchmark 评测等 API |
| ROCK CLI (`rockcli`) | 命令行工具，管理沙箱、执行命令、上传下载文件 |
| ROCK Admin | 调度节点，负责沙箱部署和资源调度 |
| ROCK Worker | 工作节点，分配物理资源给沙箱并执行运行时 |
| ROCK Envhub | 环境仓库，提供环境数据的注册和存储 |

**Harbor** 是运行在 ROCK 沙箱中的 Agent Benchmark 评测框架。开发者通过 ROCK Agent SDK 编写 `JobConfig`，由 ROCK 创建沙箱并在其中运行 Harbor 评测任务，最终收集 Trial 结果（reward、轨迹、日志等）。

## SDK 核心概念

### 包路径

```
rock.sdk.agent/
├── __init__.py              # 导出 Job, JobConfig, JobResult 等
├── constants.py             # 常量（超时、日志路径）
├── job.py                   # Job 类（提交/运行/取消评测任务）
└── models/
    ├── environment_type.py  # 环境类型枚举
    ├── orchestrator_type.py # 编排器类型枚举
    ├── job/
    │   ├── config.py        # JobConfig 及所有子配置
    │   └── result.py        # JobResult, JobStatus
    ├── metric/
    │   ├── config.py        # MetricConfig
    │   └── type.py          # MetricType 枚举
    └── trial/
        ├── config.py        # AgentConfig, VerifierConfig, TaskConfig 等
        └── result.py        # TrialResult, AgentInfo, VerifierResult
```

### 核心执行流程

```
Job(config).run()
  → 创建 ROCK 沙箱
  → 上传配置和脚本到沙箱
  → 生成 Harbor YAML + 运行脚本
  → nohup 异步执行 harbor jobs start
  → 轮询进程状态（30s 间隔）
  → 收集每个 Trial 的 result.json
  → 返回 JobResult
```

### Job 的三种运行模式

```python
# 模式 1：完整运行（提交 + 等待）
result = await Job(config).run()

# 模式 2：异步提交 + 等待
job = Job(config)
await job.submit()       # 立即返回
# ... 做其他事情 ...
result = await job.wait()

# 模式 3：取消运行中任务
await job.cancel()
```

## 配置编写指南

### 方式一：YAML 配置文件

最常用的方式，适合大多数场景。

#### 完整配置模板

```yaml
# ============ Job 身份 ============
experiment_id: "my-experiment"           # 必填：实验标识
job_name: "swe-bench-test"              # 可选：Job 名称（不设置则自动生成）
namespace: "my-team"                    # 可选：租户隔离

# ============ ROCK 环境 ============
environment:
  base_url: "<your-rock-base-url>"      # ROCK 服务地址
  # 认证（二选一）
  xrl_authorization: "<token>"          # 已弃用，推荐用 extra_headers
  extra_headers:
    Authorization: "Bearer <token>"
  # 沙箱配置
  image: "python:3.11"                  # Docker 镜像（含 harbor 时使用 harbor 镜像）
  cluster: "zb"                         # 集群标识
  memory: "16g"                         # 内存限制
  cpus: 4                               # CPU 限制
  startup_timeout: 600                  # 启动超时（秒）
  auto_clear_seconds: 3600              # 自动清理时间
  auto_stop: true                       # 完成后自动停止沙箱
  # 沙箱启动后执行的命令
  setup_commands:
    - "echo 'setup done'"
  # 运行前上传的文件
  file_uploads: []
  # 环境变量（API Key 等）
  env:
    OPENAI_API_KEY: "<your-key>"
    OPENAI_BASE_URL: "<your-base-url>"

# ============ Agent 配置 ============
agents:
  - name: "claude-code"                 # Agent 名称
    model_name: "custom_openai/gpt-4o"  # 模型名称
    override_timeout_sec: 600           # 单次超时
    max_timeout_sec: 1800               # 最大超时
    kwargs: {}                          # 额外参数
    env: {}                             # Agent 专属环境变量

# ============ 编排器 ============
orchestrator:
  type: "local"                         # local（本地）或 queue（队列）
  n_concurrent_trials: 4                # 并发 Trial 数
  quiet: false
  retry:
    max_attempts: 1                     # 失败重试次数

# ============ 验证器 ============
verifier:
  override_timeout_sec: 300
  max_timeout_sec: 600
  disable: false
  mode: "harbor"                        # harbor（默认）或 native（容器化验证器）

# ============ 数据集 ============
datasets:
  - name: "princeton-nlp/SWE-bench_Verified"
    registry:
      split: "test"
      # OSS 数据集注册中心（推荐）
      oss_access_key_id: "<key>"
      oss_access_key_secret: "<secret>"
      oss_bucket: "<bucket>"
      oss_dataset_path: "<path>"
      oss_region: "<region>"
      oss_endpoint: "<endpoint>"
    task_names: []                      # 空=全部，指定则只跑这些
    exclude_task_names: []              # 排除的任务
    n_tasks: null                       # 限制任务数量

# ============ 指标 ============
metrics: []

# ============ 标签 ============
labels:
  team: "my-team"
  version: "v1"
```

#### 常用场景模板

**SWE-bench Verified 评测：**
```yaml
experiment_id: "swe-bench-<model-name>"
environment:
  base_url: "<rock-url>"
  image: "<harbor-image:tag>"
  cluster: "zb"
  memory: "32g"
  cpus: 8
  startup_timeout: 1800
  auto_stop: true
  env:
    OPENAI_API_KEY: "<key>"
    OPENAI_BASE_URL: "<url>"

agents:
  - name: "swe-agent"
    model_name: "custom_openai/<model>"

orchestrator:
  n_concurrent_trials: 4

datasets:
  - name: "princeton-nlp/SWE-bench_Verified"
    registry:
      split: "test"
      # OSS 配置（或使用环境变量自动转发）
    task_names:
      - "astropy__astropy-7606"
```

**Terminal Bench 2 评测：**
```yaml
experiment_id: "terminal-bench-<model-name>"
environment:
  base_url: "<rock-url>"
  image: "<harbor-image:tag>"
  cluster: "zb"
  memory: "16g"
  cpus: 4
  auto_stop: true
  env:
    LLM_API_KEY: "<key>"
    LLM_BASE_URL: "<url>"

agents:
  - name: "openhands"
    model_name: "<provider>/<model>"

orchestrator:
  n_concurrent_trials: 1

datasets:
  - name: "terminal-bench-2-test"
    registry:
      split: "test"
```

### 方式二：Python SDK

适合需要程序化配置和动态参数的场景。

```python
import asyncio
from rock.sdk.agent import Job, JobConfig
from rock.sdk.agent.models.job.config import (
    RockEnvironmentConfig,
    AgentConfig,
    VerifierConfig,
    OrchestratorConfig,
    DatasetConfig,
    RegistryDatasetConfig,
)
from rock.sdk.sandbox.config import SandboxConfig

async def main():
    # 构建配置
    config = JobConfig(
        experiment_id="my-experiment",
        environment=RockEnvironmentConfig(
            base_url="<rock-url>",
            image="python:3.11",
            cluster="zb",
            memory="16g",
            cpus=4,
            auto_stop=True,
            env={"OPENAI_API_KEY": "<key>"},
        ),
        agents=[
            AgentConfig(
                name="my-agent",
                model_name="custom_openai/gpt-4o",
            )
        ],
        orchestrator=OrchestratorConfig(n_concurrent_trials=4),
        verifier=VerifierConfig(mode="harbor"),
        datasets=[
            # 通过 Registry 加载数据集
        ],
    )

    # 运行评测
    result = await Job(config).run()

    # 分析结果
    print(f"Score: {result.score}")
    print(f"Completed: {result.n_completed}/{len(result.trial_results)}")
    for trial in result.trial_results:
        print(f"  {trial.task_name}: {trial.score} ({trial.status})")

asyncio.run(main())
```

### 方式三：从 YAML 加载并修改

```python
from rock.sdk.agent import Job, JobConfig

# 加载 YAML 配置
config = JobConfig.from_yaml("job_config.yaml")

# 动态修改
config.datasets[0].task_names = ["specific-task-1", "specific-task-2"]
config.environment.memory = "32g"

# 序列化回 YAML（不含 Rock 环境字段，纯 Harbor 格式）
harbor_yaml = config.to_harbor_yaml()
```

## Agent 开发

### rock_agent_config.yaml

每个 Agent 需要一个 `rock_agent_config.yaml` 配置文件，定义安装和运行方式：

```yaml
# Agent 运行命令（${prompt} 会被替换为实际输入）
run_cmd: "claude -p ${prompt}"

# 运行时环境
runtime_env_config:
  type: node                           # node 或 python
  custom_install_cmd: "npm install -g @anthropic-ai/claude-code"
  npm_registry: "https://registry.npmmirror.com"  # 可选：npm 镜像

# 环境变量
env:
  ANTHROPIC_BASE_URL: "<url>"
  ANTHROPIC_API_KEY: "<key>"

# 可选配置
skip_wrap_run_cmd: false               # 跳过 PATH 包装
project_path: "/workspace"             # Agent 工作目录
working_dir: "/workspace"
post_init_cmds:                        # 初始化后执行的命令
  - "git config --global user.email 'bot@example.com'"
```

### 已支持的 Agent 示例

| Agent | 安装命令 | run_cmd |
|-------|---------|---------|
| Claude Code | `npm install -g @anthropic-ai/claude-code` | `claude -p ${prompt}` |
| Cursor CLI | `curl https://cursor.com/install \| bash` | `cursor-agent -p ${prompt}` |
| Qwen Code | `npm install -g @qwen-code/qwen-code@latest` | `qwen -y ${prompt}` |
| OpenHands | 通过 pip 安装 | `openhands run` |
| SWE-Agent | `pip install -e .` | `sweagent run` |

### 轻量级 Agent 运行（非 Benchmark）

适合快速测试 Agent，不需要完整 Benchmark 流程：

```python
import asyncio
from rock.sdk.sandbox.client import Sandbox
from rock.sdk.sandbox.config import SandboxConfig

async def main():
    sandbox = Sandbox(SandboxConfig())
    await sandbox.start()
    await sandbox.agent.install()    # 根据 rock_agent_config.yaml 安装
    result = await sandbox.agent.run("Hello, solve this bug")
    print(f"result={result}")
    await sandbox.stop()

asyncio.run(main())
```

## 配置详解

### 数据集 Registry 类型

| 类型 | 说明 | 适用场景 |
|------|------|---------|
| `OssRegistryInfo` | 阿里云 OSS 数据集 | 内部 Benchmark（推荐） |
| `RemoteRegistryInfo` | 远程注册中心（默认 GitHub） | 开源 Benchmark |
| `LocalRegistryInfo` | 本地文件系统 | 本地开发和调试 |

### 环境类型

| 类型 | 说明 |
|------|------|
| `docker` | Docker 容器（默认） |
| `rock` | ROCK 沙箱 |
| `daytona` / `e2b` / `modal` / `runloop` / `gke` | 第三方沙箱 |

### 编排器类型

| 类型 | 说明 |
|------|------|
| `local` | 本地编排，Trial 在沙箱内顺序/并发执行 |
| `queue` | 队列编排，适合大规模分布式评测 |

## 结果分析

### JobResult 结构

```python
class JobResult:
    job_id: str
    status: JobStatus           # pending/running/completed/failed/cancelled
    labels: dict[str, str]
    trial_results: list[TrialResult]
    raw_output: str
    exit_code: int

    @property
    def score(self) -> float    # 所有 Trial 的平均分
    @property
    def n_completed(self) -> int
    @property
    def n_failed(self) -> int
```

### TrialResult 结构

```python
class TrialResult:
    task_name: str
    trial_name: str
    agent_info: AgentInfo       # Agent 名称、版本、模型
    agent_result: AgentResult   # token 使用量、成本、rollout
    verifier_result: VerifierResult  # rewards 字典
    exception_info: ExceptionInfo    # 异常信息

    @property
    def score(self) -> float    # verifier_result.rewards["reward"]
    @property
    def status(self) -> str     # "failed" 或 "completed"
    @property
    def duration_sec(self) -> float
```

### 结果分析示例

```python
result = await Job(config).run()

# 总分
print(f"平均分: {result.score}")

# 逐 Trial 分析
for trial in result.trial_results:
    if trial.status == "failed":
        print(f"❌ {trial.task_name}: {trial.exception_info.exception_type}")
    else:
        print(f"✅ {trial.task_name}: reward={trial.score}, 耗时={trial.duration_sec:.1f}s")

# 失败率
print(f"失败率: {result.n_failed}/{len(result.trial_results)}")
```

## 环境变量自动转发

以下 OSS 环境变量会自动从宿主进程转发到沙箱，无需在 YAML 中写入：

- `OSS_ACCESS_KEY_ID`
- `OSS_ACCESS_KEY_SECRET`
- `OSS_REGION`
- `OSS_ENDPOINT`
- `OSS_BUCKET`
- `OSS_DATASET_PATH`

## 常见问题

### Q: 如何选择内存和 CPU 配置？

| Benchmark | 推荐 memory | 推荐 cpus |
|-----------|------------|-----------|
| SWE-bench Verified | 32g | 8 |
| Terminal Bench 2 | 16g | 4 |
| 轻量测试 | 8g | 2 |

### Q: timeout_multiplier 怎么设置？

默认 1.0。如果 Agent 经常超时，可设为 1.5~2.0。总等待超时 = agent_timeout * multiplier + 600s（环境启动 + 数据下载 + verifier 缓冲），默认回退上限 7200s（2 小时）。

### Q: 如何只跑特定任务？

在 `datasets` 中指定 `task_names`：
```yaml
datasets:
  - name: "princeton-nlp/SWE-bench_Verified"
    registry: { ... }
    task_names:
      - "astropy__astropy-7606"
      - "django__django-12345"
```

### Q: 如何使用 Native Verifier？

```yaml
verifier:
  mode: "native"
```

Native 模式支持容器化验证器，适合需要独立环境的测试场景。

### Q: OSS 数据集配置太长怎么办？

利用环境变量自动转发，在运行前 export OSS 环境变量即可，YAML 中可省略 OSS 字段。
