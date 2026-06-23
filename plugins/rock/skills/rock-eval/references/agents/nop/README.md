# Nop Agent

## 定位
空实现 agent，源码在 `src/harbor/agents/nop.py`。适合调度链路、环境生命周期和 verifier 容错测试。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| 无 | 没有专属 `kwargs`。 | `src/harbor/agents/nop.py` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| 无 | `agent.env`、`model_name` 都不会影响行为。 | `src/harbor/agents/nop.py::NopAgent.run` |

## Harbor job YAML 样例
```yaml
jobs_dir: jobs/nop
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
  - name: nop
    override_timeout_sec: 60
    override_setup_timeout_sec: 60
    max_timeout_sec: 120
    env: {}
    kwargs: {}

datasets:
  - name: your-dataset
    registry:
      split: test
    task_names:
      - task-id-1
```

## 安装、运行与产物的源码入口
### 安装入口
- `src/harbor/agents/nop.py::NopAgent.setup`：空实现。

### 运行与产物入口
- `src/harbor/agents/nop.py::NopAgent.run`：空实现。

## 对 instance 的依赖要求
- 没有额外依赖。
- 只有 verifier 仍会依赖 task 环境本身。

## 文档更新时优先关注
- `src/harbor/agents/nop.py`

## 差异与取舍
### 优点
- 最快、最干净。
- 很适合基础设施压测。

### 缺点
- 没有任何求解能力。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
