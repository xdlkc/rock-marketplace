# 全量回归 SOP

基于 `regression.py` 的标准操作流程，覆盖：发起回归 → 监控进度 → 查看报告 → 排查失败 → 重跑修复。

---

## 流程总览

```
run  ──→  report  ──→  sync(可选)  ──→  diagnose  ──→  retry
 ↑                                                        │
 └────────────────────────────────────────────────────────┘
```

| 步骤 | 子命令 | 目的 |
|------|--------|------|
| 1. 发起回归 | `run` | 派发全量任务，产出结果 JSON |
| 2. 查看报告 | `report` | 状态汇总 / Reward 分布 / 耗时 / 异常分类 |
| 3. 同步状态 | `sync` | 刷新 dispatched/reward 缺失的任务 |
| 4. 排查失败 | `diagnose` | 异常分组总览 + 单任务深入 |
| 5. 重跑失败 | `retry` | 按异常类型/状态筛选重跑 |

---

## 1. 发起回归 (`run`)

### 必传参数

| 参数 | 说明 |
|------|------|
| `--bench` | Bench 模板名称（如 `aone-bench`） |
| `--agent` | Agent 名称（如 `claude-code`、`mini-swe-agent`） |
| `--window-size` | **全局并发上限（滑动窗口）**：始终维持 N 个任务在飞，一个完成立刻补一个。建议 **~10**（ROCKCLI 共享配额——更高并发可能触发限流并影响他人，脚本本身无硬性上限）。`0` = 不限制（全部并行） |
| `--concurrency` | （兼容旧参数）与 `--window-size` 同义；两者同时给定时取较小值 |

> `--window-size` 限制的是「同时在飞的任务数」，**没有分批 barrier**——整个回归过程吞吐量始终维持在并发上限，不会出现「等满一批再开下一批」的空窗。`--dataset` 和 `--split` 在不指定 `--tasks` 时必传。

### 配置保存与复用（`--save-config` / `--from-config`）

每次 `run` / `retry` 都会**自动**把本次完整配置快照到 `configs/<experiment-id>.json`
（与 `results/`、`logs/` 同级），方便追溯每次回归用了什么参数。另外两个 flag 支持存到
自定义路径和从文件复跑：

```bash
# 把当前配置存成可复用模板
python3 regression.py run --bench <BENCH> --agent <AGENT> --dataset <D> --split <S> \
  --concurrency 5 --window-size 0 --image <IMG> --ee K=V \
  --save-config ./my-template.json

# 之后用模板复跑：只传想覆盖的参数，其余从 JSON 取
python3 regression.py run --from-config ./my-template.json --concurrency 8
```

**合并语义**：JSON 是基底，CLI 显式传的参数覆盖 JSON 同名字段（没传的字段用 JSON 的值）。
指定 `--from-config` 后，`--bench` / `--agent` 不再强制要求从 CLI 传入（可来自文件）。
JSON 存的是全部 run 参数，**不含** experiment id（每次按 dataset + 时间戳重新生成）。注意
`--config` 是 rc 的 JobConfig YAML，与本节无关。

### 当用户只给 bench 名字时，先反查数据集再取 task

用户常常只说一个 bench 名（不给 dataset/split）。此时**不要猜数据集**，按下面顺序确认：

1. `rc agent bench getconfig <BENCH> --raw` 看 template 的 `datasets` 字段，拿到数据集
   `name`、`registry.split`、`task_names`。
2. 用反查到的 dataset + split 跑 `rc datasets <NAME> tasks --split <SPLIT>` 获取 task 列表，
   再把 dataset/split 传给 `regression.py run`（或把 task 列表用 `--tasks` 传）。
3. **回退**：有的 bench 的数据集不支持 `tasks` 子命令（查不到 task）。此时改用 template
   `--raw` 输出里 `datasets[].task_names` 的内嵌列表作为 task 来源。不要凭空假设，先
   实际看一眼 `--raw` 输出再决定。

> harbor 类 bench（如 `harborframework/*`）template 必有 `datasets.name`，第 1-2 步对它们
> 稳定可用。命令与 YAML 结构详见 `references/rockcli-cheatsheet.md`。

### Agent / Bench 取值 — 实时查询，不要写死

rockcli 会持续升级，支持的 agent 和 bench 列表随版本变化。**不要依赖本文档里的固定
清单**——用前先跑 `rc agent run --help` 查看当前支持的 `--agent` / `--bench` 取值
（帮助里的"常用取值"段），以实际输出为准。bench 模板还可用
`rc agent deps sync benchhub` 更新。

其中两个 `--agent` 是语义稳定的 **baseline**（用途不随版本变）：

| Agent | 说明 |
|-------|------|
| `oracle` | **上界 baseline**：直接提交正确答案，用于验证评分/环境链路 |
| `nop` | **下界 baseline**：不做任何操作，用于验证派发/环境链路 |

### ⚠️ 全量回归前先做环境验证（oracle / nop）

`oracle` 和 `nop` 是两个特殊的 baseline agent，**不是真正跑评估**，而是用来快速验证
镜像/集群/数据集/评分链路是否通畅。**在发起任何全量回归（用真实 agent 跑整个数据集）
之前，必须先询问用户：是否要先用 `oracle` 和/或 `nop` 小批量跑几条任务验证环境？**

- `oracle` 跑通 → 评分链路、reward 计算正常（理论上 reward 应接近满分）
- `nop` 跑通 → 任务派发、沙箱启动、镜像/集群配置正常（reward 应为 0/下界）
- 两者都跑通后，再用真实 agent 发起全量回归，避免环境问题导致整批失败、浪费资源

验证示例（用 `--tasks` 选几条代表性任务，小并发）：

```bash
# 先用 oracle 验证评分链路
python3 regression.py run --bench aone-bench --tasks <task1>,<task2> \
  --agent oracle --concurrency 2 --window-size 0 [其他经用户确认的环境参数]

# 再用 nop 验证派发/环境链路
python3 regression.py run --bench aone-bench --tasks <task1>,<task2> \
  --agent nop --concurrency 2 --window-size 0 [其他经用户确认的环境参数]
```

### rockcli 透传参数（需先与用户确认）

镜像、集群、模型、规格等环境/运行参数直接**按用户指定的值**透传给 `rc agent run`。
**不要自行假定或注入任何默认值**——发起回归前先向用户确认需要设置哪些参数，
只透传用户明确提供的 flag；用户未提供的参数一律不传。

| 参数 | 说明 |
|------|------|
| `--dataset` | 数据集名称 |
| `--split` | 数据集 split |
| `--image` | Docker 镜像 |
| `--cluster` | 集群标识 |
| `--model` | 模型名称（**可不填，不填则用 ROCKCLI 共享模型**） |
| `--api-key` | API 密钥 |
| `--ee KEY=VALUE` | 沙箱环境变量，可多次传 |
| `--set path=value` | YAML 字段覆盖，可多次传 |
| `--pre` / `--no-pre` | 预发 / 正式环境（脚本默认 `--pre` 预发） |
| `--namespace` | ROCK 项目空间 |
| `--cpus` | CPU 规格（Core） |
| `--memory` | 内存规格（GiB） |
| `--with-companion` | 启用陪跑助手（透传为 rc `--with`，当前支持 `claude-code`） |
| `--config` | JobConfig YAML 配置文件路径 |
| `--async-mode` | 异步模式（透传为 rc `--async`） |
| `--user-id` | 用户 ID（工号） |
| `--base-url` | 服务端地址（rc 默认 `http://xrl.alibaba-inc.com`） |

> 说明：上表是 `regression.py` 的参数名，部分会翻译成不同的 rc flag（`--with-companion`→`--with`、`--async-mode`→`--async`）。`--pre` 是脚本固有默认（默认预发），属脚本行为，不在"需向用户确认"之列；需要确认的是镜像/集群/模型/规格/环境变量等环境参数。

### 调度控制参数

| 参数 | 说明 |
|------|------|
| `--resume` | 续跑模式（跳过已有 success + error 的任务） |
| `--tasks t1,t2,...` | 手动指定任务列表（此时 dataset/split 可省略） |
| `--poll-interval` | 轮询间隔秒数（默认 10） |
| `--poll-timeout` | 轮询超时秒数（默认 600） |

### 示例

```bash
# 标准全量回归
python3 regression.py run \
  --bench aone-bench \
  --dataset alibaba/aone-bench-java100 \
  --split delivery_0609-cn \
  --agent claude-code \
  --concurrency 10 \
  --window-size 0

# 指定镜像 + 模型 + 环境变量
python3 regression.py run \
  --bench aone-bench \
  --dataset alibaba/aone-bench-java100 \
  --split delivery_0609-cn \
  --agent mini-swe-agent \
  --concurrency 10 \
  --window-size 0 \
  --image rock-registry-vpc.cn-shanghai.cr.aliyuncs.com/harbor/harbor:33180a83 \
  --model glm-5.1 \
  --ee OPENAI_API_KEY=sk-xxx \
  --ee OPENAI_BASE_URL=https://evamux.alibaba-inc.com/v1

# 续跑（跳过 success + error）
python3 regression.py run --resume \
  --bench aone-bench \
  --dataset alibaba/aone-bench-java100 \
  --split delivery_0609-cn \
  --agent claude-code \
  --concurrency 10 \
  --window-size 0
```

### 产出

- 结果文件：`results/<dataset>-<timestamp>.json`
- 日志目录：`logs/<dataset>-<timestamp>/`

---

## 2. 查看报告 (`report`)

```bash
# 查看最新实验（文本）
python3 regression.py report

# 指定实验 ID
python3 regression.py report aone-bench-java100-20260613_002258

# 指定结果文件
python3 regression.py report ./results/aone-bench-java100-20260613_002258.json

# JSON 格式（供脚本消费）
python3 regression.py report --format json

# 生成 HTML 可视化报告并打开浏览器
python3 regression.py report --format html --open
```

### 报告内容

| 区块 | 说明 |
|------|------|
| Header | 实验元信息（bench/dataset/split/agent/model/时间） |
| 状态汇总 | success/error/dispatched 计数 + 百分比 + 进度条 |
| Reward 分布 | min/max/mean/median/P25/P75/std + 直方图 |
| 耗时分布 | min/max/mean/median/P25/P75 |
| 异常分类 | 按 exception_type 分组计数 + 示例任务 |
| 未完成告警 | dispatched 任务提示运行 sync |

---

## 3. 同步状态 (`sync`)

用于回归中断或轮询超时后，从服务端刷新任务最新状态。

```bash
# 同步最新实验中的 dispatched 任务
python3 regression.py sync

# 指定实验
python3 regression.py sync aone-bench-java100-20260613_002258

# 预览变更，不实际写入
python3 regression.py sync --dry-run

# 强制重新同步所有任务（含已完成的）
python3 regression.py sync --force
```

### 同步逻辑

1. 筛选 dispatched 或 reward=null 的任务
2. 通过 `rc agent view` 查询服务端最新状态
3. 无 job_name 的 dispatched 任务标记为 error
4. 更新结果 JSON 并打印变更摘要

> 长跑 job 的定时巡检（Cron 每 3 分钟 sync + report + 判可疑，可疑时调 rock-agent-debug 深挖确认）见
> `SKILL.md` § Monitor 巡检机制 与 `references/team-orchestration.md` § Monitor。本节不展开，只做指向。

---

## 4. 排查失败 (`diagnose`)

### 总览模式 — 快速定位高频问题

```bash
# 全量异常总览
python3 regression.py diagnose

# 只看 error 状态
python3 regression.py diagnose --status error

# 只看特定异常类型
python3 regression.py diagnose --exception RuntimeError
```

输出内容：
- 按 exception_type 分组（计数 + 占比）
- 去重后的 exception_message 模式（归一化变量部分）
- 卡住的 dispatched 任务列表

### 单任务深入 — 查看具体原因

```bash
# 查看单个任务详情 + 本地日志
python3 regression.py diagnose --task codereview-21491816

# 拉取远程日志
python3 regression.py diagnose --task codereview-21491816 --remote

# 查看执行轨迹
python3 regression.py diagnose --task codereview-21491816 --trajectory

# 查看产物清单
python3 regression.py diagnose --task codereview-21491816 --artifacts

# 本地日志只看最后 50 行
python3 regression.py diagnose --task codereview-21491816 --tail 50
```

---

## 5. 重跑失败 (`retry`)

与 `--resume` 的区别：

| | `run --resume` | `retry` |
|---|---|---|
| 跳过范围 | success + error | 只跳过 success |
| 实验 ID | 沿用原 ID | 新建 ID（含 `retry_of` 引用） |
| 筛选能力 | 无 | 按状态 / 异常类型 / 手动指定 |

```bash
# 重跑所有失败任务（error + dispatched）
python3 regression.py retry aone-bench-java100-20260613_002258 \
  --bench aone-bench \
  --agent claude-code \
  --concurrency 10 \
  --window-size 0

# 只重跑 error 状态
python3 regression.py retry --filter error \
  --bench aone-bench --agent claude-code --concurrency 10 --window-size 0

# 只重跑特定异常类型
python3 regression.py retry --filter error --exception-type RewardFileNotFoundError \
  --bench aone-bench --agent claude-code --concurrency 10 --window-size 0

# 手动指定重跑任务
python3 regression.py retry --tasks codereview-123,codereview-456 \
  --bench aone-bench --agent claude-code --concurrency 5 --window-size 0
```

---

## 典型工作流

### 场景 A：正常回归

> 发起前先与用户确认 bench、dataset、split、agent、concurrency，以及镜像/集群/模型/
> 规格/环境变量等透传参数——不要自行假定默认值，只透传用户指定的参数。
> 并询问用户是否先用 `oracle` / `nop` 小批量验证环境（见上文"环境验证"节）。

```bash
# 0.（可选，建议）先用 oracle / nop 小批量验证环境，确认通过后再发起全量
python3 regression.py run --bench aone-bench --tasks <task1>,<task2> \
  --agent oracle --concurrency 2 --window-size 0
python3 regression.py run --bench aone-bench --tasks <task1>,<task2> \
  --agent nop --concurrency 2 --window-size 0

# 1. 发起全量（以下参数均按用户确认结果填写）
python3 regression.py run --bench aone-bench --dataset alibaba/aone-bench-java100 \
  --split delivery_0609-cn --agent claude-code --concurrency 10 --window-size 0

# 2. 查看报告
python3 regression.py report --format html --open
```

### 场景 B：回归中断恢复

```bash
# 1. 同步中断前已派发的任务状态
python3 regression.py sync

# 2. 查看当前状态
python3 regression.py report

# 3. 续跑未完成的任务
python3 regression.py run --resume --bench aone-bench --dataset alibaba/aone-bench-java100 \
  --split delivery_0609-cn --agent claude-code --concurrency 10 --window-size 0
```

### 场景 C：失败排查 + 定向重跑

```bash
# 1. 看异常分布
python3 regression.py diagnose

# 2. 深入看具体任务
python3 regression.py diagnose --task codereview-21491816 --remote --trajectory

# 3. 重跑特定异常类型
python3 regression.py retry --filter error --exception-type RuntimeError \
  --bench aone-bench --agent claude-code --concurrency 10 --window-size 0

# 4. 查看重跑结果
python3 regression.py report --format html --open
```

---

## 文件结构

```
results/
  ├── aone-bench-java100-20260613_002258.json      # 结果数据
  └── aone-bench-java100-20260613_002258.html      # 可视化报告
logs/
  └── aone-bench-java100-20260613_002258/
      ├── codereview-21491816.log                   # 单任务日志
      └── ...
```
