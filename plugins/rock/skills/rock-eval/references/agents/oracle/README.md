# Oracle Agent

## 定位
直接执行任务自带 `solution/solve.sh` 的标准答案执行器，源码在 `src/harbor/agents/oracle.py`。适合回归环境、验证 verifier 和对拍标准答案。

## 参数与源码入口
共享字段的完整源码入口见 [../README.md](../README.md) 里的共享参数表。

### Agent 专属参数
| 参数 | 说明 | 源码入口 |
| --- | --- | --- |
| `agent.env` | 与 task 的 `solution.env` 一起注入 `solve.sh`。 | `src/harbor/agents/oracle.py::OracleAgent.run`；`src/harbor/utils/env.py::resolve_env_vars` |
| `task_dir` / `trial_paths` | Harbor 内部注入，不建议在 job YAML 里手动配。 | `src/harbor/agents/oracle.py::OracleAgent.__init__` |

### 相关环境变量与 task 环境入口
| 变量 / 入口 | 作用 | 源码入口 |
| --- | --- | --- |
| `solution.env` | task 标准答案脚本自己的环境变量。 | `src/harbor/models/task/config.py::SolutionConfig`；`src/harbor/agents/oracle.py::OracleAgent.run` |

## Harbor job YAML 样例
```yaml
# Oracle 不依赖模型凭证。
jobs_dir: jobs/oracle
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
    ORACLE_MODE: baseline
  kwargs: {}

agents:
  - name: oracle
    override_timeout_sec: 600
    override_setup_timeout_sec: 60
    max_timeout_sec: 1200
    env:
      EXTRA_FLAG: value
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
- `src/harbor/agents/oracle.py::OracleAgent.setup`：空实现，没有安装脚本。

### 运行与产物入口
- `src/harbor/agents/oracle.py::OracleAgent.run`：上传 `solution/` 后执行 `solve.sh`。
- `src/harbor/models/trial/paths.py`：`oracle.txt` 与 `exit-code.txt` 的落盘位置。

## 对 instance 的依赖要求
- 必须存在 `solution/solve.sh`。
- 任务实例要自己带齐语言运行时和依赖。
- 没有额外 CLI、Python 或 Node 安装要求。

## 文档更新时优先关注
- `src/harbor/agents/oracle.py`
- `src/harbor/models/task/config.py::SolutionConfig`

## 差异与取舍
### 优点
- 确定性最强，最适合环境回归。
- 零模型成本，排障简单。

### 缺点
- 没有自主求解能力。
- 没有 ATIF 轨迹。

建议先按本页“文档更新时优先关注”里的入口扫源码 diff，再决定 README 是否需要同步改动。
