# Deep Analysis — 实验失败深度分析

使用 `rockcli`（`rc`）对 bench 实验中的失败 job 做系统性 trajectory 分析，输出 per-task 根因报告和汇总摘要。

---

## Phase 1：实验概览

> **重要说明**：`rc agent view -e <EXP_ID> --limit 200` 会报 422 错误（API 上限 100 条/页），
> `rc agent view -j <JOB> -o json` 对大型 job 输出经常被截断（~50/89 job 出现此问题），
> 因此概览阶段**不依赖** `-o json` 获取 per-job 详情。改用 `live-score.py` 作为数据源。

### 1.1 定位 live-score.py

```bash
find ~/.claude/plugins -path "*/rock-eval/scripts/live-score.py" 2>/dev/null
```

记录路径，后续用 `<LIVE_SCORE_PATH>` 表示。

### 1.2 运行 live-score.py 获取实验概览

```bash
python3 <LIVE_SCORE_PATH> -e <EXP_ID> [--pre] --text
```

输出包含：Score、Pass Rate、每个任务的 Status/Pass%/Trials/AvgR 列。

也可使用辅助脚本（自动发现 live-score.py 并生成结构化 JSON）：

```bash
python3 scripts/fetch-overview.py <EXP_ID> [--pre] \
  --output /tmp/bench-analysis-<EXP_ID>/overview.json
```

`--live-score-path <path>` 可在自动发现失败时显式指定 live-score.py 路径。

### 1.3 创建输出目录

```bash
mkdir -p /tmp/bench-analysis-<EXP_ID>
```

### 1.4 区分需分析的 job

从 live-score.py 输出中识别：

- **需深度分析**：`avg_reward < 1.0` 或 `status == error`（且 `n_completed > 0`）
- **跳过**：`status == running` 且 `n_completed == 0`（infra 问题或仍在运行，记为"无数据"）
- **仅计入统计**：`avg_reward == 1.0` 的成功 job

输出格式（`overview.json`）包含：`total_jobs`, `passed`, `failed`, `score`, `jobs_to_analyze`。

### 1.5 任务分类

在 §1.4 得到 `jobs_to_analyze` 列表后，进一步将每个待分析 job 归入以下类型：

| 类型标签 | 判定条件 | 分析模板 |
|----------|----------|----------|
| `zero_score` | `avg_reward == 0` 且无 exception | 模板 A：零分任务深度归因报告 |
| `abnormal` | 有 exception 且 `avg_reward > 0` | 模板 B：异常任务诊断报告 |
| `zero_plus_abnormal` | `avg_reward == 0` 且有 exception | 模板 C：零分+异常综合诊断报告 |
| `partial` | `0 < avg_reward < 1` 且无 exception | 沿用原有 Step D 模板 |

判定逻辑：

```python
for job in jobs_to_analyze:
    has_exception = job["n_errors"] > 0 or job["status"] == "error"
    is_zero = (job["avg_reward"] is not None and job["avg_reward"] == 0)

    if is_zero and not has_exception:
        job["analysis_type"] = "zero_score"
    elif has_exception and not is_zero:
        job["analysis_type"] = "abnormal"
    elif is_zero and has_exception:
        job["analysis_type"] = "zero_plus_abnormal"
    else:
        job["analysis_type"] = "partial"
```

> **注意**：文本模式解析时 `n_errors` 可能为 0（`fetch-overview.py` 的文本解析限制），需同时检查 `status == "error"` 作为有异常的补充判断。

分类结果随 job 信息一起传递给 Phase 2 子 agent prompt，子 agent 据此选择 `references/report-templates.md` 中的对应模板。

---

## Phase 2：并行深度分析

**使用 Agent 工具派发子 agent，每批 5~8 个 job 并行分析。**
主上下文只协调与汇总，不自行读取 trajectory。

> **关键限制**：**不要**使用 `rc agent view -j <JOB> -o json`——对大型 job 会在 JSON 中途截断，导致解析失败。
> 改用文本格式获取 job 概览，用 `rc agent fs cat` 读取具体文件。

**派发子 agent 时的注意事项：**
- 在 prompt 中明确要求子 agent 先执行 `mkdir -p /tmp/bench-analysis-<EXP_ID>`
- 明确指示子 agent 最后用 **Write 工具**将分析结果写入文件，而非仅在对话中输出
- 使用 `mode: "bypassPermissions"` 或 `mode: "auto"` 以避免子 agent 被权限提示阻塞

### 子 agent 分析流程（每个失败 job）

#### Step A：获取 job 概览（文本格式，不加 `-o json`）

```bash
# 获取 job 概览（文本格式，可靠不截断）
rc agent view -e <EXP_ID> -j <JOB_NAME> [--pre]

# 列出所有 trial
rc agent fs ls -e <EXP_ID> -j <JOB_NAME> [--pre]
```

从输出中找到 reward < 1.0 的 trial 名称。若有多个失败 trial，优先分析：
1. 有非零 reward 的 trial（partial failure 比完全失败更有信息量）
2. 有 exception 的 trial（定位错误更明确）
3. 其余：取第一个完成的 trial

#### Step B：读取每个失败 trial 的数据

```bash
# result.json（必读）
rc agent fs cat <TRIAL>/result.json -e <EXP_ID> -j <JOB_NAME> [--pre]

# exception.txt（有异常时读）
rc agent fs cat <TRIAL>/exception.txt -e <EXP_ID> -j <JOB_NAME> [--pre]

# verifier 输出（reward=0 且无异常时读）
rc agent fs cat <TRIAL>/verifier/test-stdout.txt -e <EXP_ID> -j <JOB_NAME> [--pre]
rc agent fs cat <TRIAL>/verifier/test-stderr.txt -e <EXP_ID> -j <JOB_NAME> [--pre]
```

**补充数据采集（`zero_score` 和 `zero_plus_abnormal` 类型需要）**：

```bash
# RT 参数：从 result.json 中提取 config / agent_config 部分
# 重点关注：
#   - temperature / top_p
#   - thinking_budget / reasoning_effort / max_thinking_tokens
#   - max_tokens / max_output_tokens
#   - override_timeout_sec / max_timeout_sec
#   - memory / cpus（若有）
#   - concurrency

# 若 result.json 中无完整 config，从 bench 模板获取默认参数：
rc agent bench getconfig <BENCH> --raw
```

```bash
# 资源消耗：从 result.json 中提取
#   - token_usage（prompt_tokens / completion_tokens / total_tokens）
#   - cost（若有）
#   - agent_execution.duration_sec
#   - trajectory steps 数量（作为 API 调用次数的近似）
```

#### Step C：获取 trajectory 和异常详情（按任务类型）

**对 `zero_score` 和 `partial` 类型**——完整 trajectory 分析：

```bash
# 首选：格式化文本视图（不加 -o json，避免截断）
rc agent view -e <EXP_ID> -j <JOB_NAME> [--pre] --trajectory

# 若格式化视图仍被截断，下载原始 JSON 文件
rc agent fs download <TRIAL>/agent/trajectory.json \
  -e <EXP_ID> -j <JOB_NAME> -o /tmp/bench-analysis-<EXP_ID>/ [--pre]
```

**对 `abnormal` 类型**——异常根因分析为主，无需完整 trajectory：

```bash
# 必读：exception.txt（已在 Step B 获取）
# 必读：result.json（已在 Step B 获取）

# 可选：run.log（获取更详细的错误上下文）
rc agent fs cat run.log -e <EXP_ID> -j <JOB_NAME> [--pre]

# 可选：检查同实验其他 job 是否有相同异常（判断系统性问题）
# 此信息从 Phase 1 overview 数据或主上下文传入
```

**对 `zero_plus_abnormal` 类型**——两者都需要：

```bash
# 异常数据（已在 Step B 获取）
# 完整 trajectory（同 zero_score 类型）
rc agent view -e <EXP_ID> -j <JOB_NAME> [--pre] --trajectory

# run.log（获取异常上下文）
rc agent fs cat run.log -e <EXP_ID> -j <JOB_NAME> [--pre]
```

**Trajectory 分析要点（对照 ATIF-v1.6 schema）：**

1. **任务目标**：从第一个 `source=user` 消息提取任务描述
2. **执行路径**：逐步追踪 `tool_calls` 和 `observation.results`
3. **关键转折**：找到分数开始偏离正确路径的 `step_id`
4. **自我恢复**：agent 是否识别到错误？尝试了哪些补救？
5. **失败归因**：参照 `references/failure-taxonomy.md` 分类
6. **关键节点标注**（`zero_score` 和 `zero_plus_abnormal` 类型）：
   - 🔴 首次偏离正确路径的步骤
   - 🟡 自我纠错尝试（若有多次，逐一标注）
   - 🔵 最终失败点（或被异常中断的步骤）

#### Step D：写入 per-task 分析文件

路径：`/tmp/bench-analysis-<EXP_ID>/<task_name>.md`

**根据 §1.5 的任务分类，选择对应的报告模板**：

| `analysis_type` | 使用模板 | 来源 |
|-----------------|---------|------|
| `zero_score` | 模板 A：零分任务深度归因报告 | `references/report-templates.md` §模板 A |
| `abnormal` | 模板 B：异常任务诊断报告 | `references/report-templates.md` §模板 B |
| `zero_plus_abnormal` | 模板 C：零分+异常综合诊断报告 | `references/report-templates.md` §模板 C |
| `partial` | 下方原有模板 | 本节内嵌 |

**对 `partial` 类型**（`0 < reward < 1`，沿用现有模板）：

````markdown
# Task: <task_name>

## 基本信息
- Job: <job_name>
- Agent: <agent_name> / Model: <model_name>
- Reward: <avg_reward> | Duration: <duration_sec>s
- Status: <status>
- Trials: <n_trials> 总 / <n_errors> 错误

### 快速查看命令
```bash
# 查看 job 概览
rc agent view -e <EXP_ID> -j <job_name> [--pre]

# 查看 trajectory
rc agent view -e <EXP_ID> -j <job_name> [--pre] --trajectory

# 列出所有 trial 文件
rc agent fs ls -e <EXP_ID> -j <job_name> [--pre]

# 查看指定 trial 的 result.json
rc agent fs cat <trial_name>/result.json -e <EXP_ID> -j <job_name> [--pre]
```

## 任务目标
<从 trajectory 第一个 user 消息提取，或从 task 描述字段提取>

## Agent 执行摘要
- Step N: <动作摘要>
- Step N: <动作摘要>
（保留 5~10 个关键步骤，聚焦转折点）

## 失败分析

### 失败分类
<策略错误 / 能力不足 / 理解偏差 / 环境问题 / 超时 / 基础设施错误 / 验证器问题>

### 关键转折点
Step <step_id>：<描述发生了什么，为什么这一步导致失败>

### 根因分析
<详细说明 WHY 模型失败——不只是"做错了什么"，而是背后的根本原因>

### 正确路径
<如果要解决这个任务，正确的做法应该是什么>

## 原始数据
- Trajectory steps: <N>
- Token usage: <prompt_tokens> prompt / <completion_tokens> completion
- Exception: <exception_type 或 "无">
- Trial reward 明细: <trial_name>=<reward>, ...
````

**写入注意事项**：
- 使用 **Write 工具**将分析结果写入文件，不要仅在对话中输出
- 先执行 `mkdir -p /tmp/bench-analysis-<EXP_ID>`
- 模板中所有 `{placeholder}` / `<placeholder>` 都必须替换为实际值；无数据时写"N/A"或"无"

---

## Phase 3：失败模式聚合

所有子 agent 完成后，主上下文读取所有 per-task 分析文件，聚合失败模式。

### 失败分类（参见 `references/failure-taxonomy.md` 完整定义）

| 分类 | 描述 |
|------|------|
| 策略错误 | agent 采用了根本错误的方法 |
| 能力不足 | agent 理解任务但无法执行 |
| 理解偏差 | agent 误解了任务要求 |
| 环境问题 | docker/沙箱/网络等基础设施问题 |
| 超时 | 执行超时，未完成 |
| 基础设施错误 | API 错误、沙箱崩溃 |
| 验证器问题 | 任务已完成但 verifier 未识别 |
| 部分完成 | 完成了部分子任务但未达到全分 |

### 写入汇总报告

路径：`/tmp/bench-analysis-<EXP_ID>/SUMMARY.md`

```markdown
# Bench 回归分析报告

## 实验概览
- 实验 ID: <EXP_ID>
- 环境: staging / prod
- Agent: <agent_name> / Model: <model_name>
- 总任务数: N | 通过(reward=1.0): N | 失败: N
- Score: X.XX (per-task avg_reward 的均值)
- 分析时间: <timestamp>

## 失败模式分布

| 模式 | 数量 | 占比(失败) | 典型案例 |
|------|------|-----------|---------|
| 策略错误 | N | X% | task-a, task-b |
| 能力不足 | N | X% | task-c |
| ... | | | |

## 高频失败模式详解

### 1. <pattern_name>（N 个任务）
<这些失败的共同线索>

**代表性案例：**
- `<task_name>`：<一句话摘要>

**潜在改进方向：**
<针对这种失败模式，模型或评估配置可以改进什么>

### 2. ...

## 改进建议
1. <具体建议，优先级最高>
2. ...

## 附录：各任务分析文件索引

| 任务 | Reward | 失败分类 | 分析文件 |
|------|--------|---------|---------|
| <task_name> | <reward> | <category> | <task_name>.md |
| ... | | | |

## 成功任务列表
<task_name1>, <task_name2>, ... (reward=1.0，不做深分析)
```

---

## 实现注意事项

### 并行度控制
- 每批派出 5~8 个子 agent 并行分析
- 等待一批完成后再派下一批，避免过载

### Trajectory 大小处理
- 优先用格式化视图 `--trajectory`
- 若步数超过 100 步，重点读前 20 步（建立任务上下文）+ 最后 20 步（找失败点）+ 中间关键转折附近的步骤
- 若需原始 JSON，下载后只解析 `steps[*].tool_calls` 和 `steps[*].observation` 的摘要

### 输出语言
所有分析文件和报告使用**简体中文**。

### 仅分析失败任务
reward = 1.0 的成功任务只记录在 SUMMARY 附录中，不做 trajectory 分析。

---

## 参考文件

以下路径均相对于 rock-eval skill 根目录：

| 路径 | 用途 |
|------|------|
| `references/failure-taxonomy.md` | 失败分类定义、识别方法、边界案例处理指南 |
| `scripts/fetch-overview.py` | 实验概览解析脚本，输出待分析 job 列表 |
| `scripts/live-score.py` | 实验实时分数查询，fetch-overview.py 依赖此脚本 |
| `references/report-templates.md` | 零分/异常/合并报告模板定义，Phase 2 子 agent 按任务类型选用 |
