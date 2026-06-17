# rock-eval Agent Team TeamCreate Runbook

> 本文是 TeamCreate 模式的**运行态 runbook**：把 7 角色并行 pipeline 沉淀到 CC 原生
> `TeamCreate` + `TaskList` + `SendMessage` 上，让任务状态机驱动控制流、跨会话可恢复。
> 设计依据：`docs/superpowers/specs/2026-06-17-rock-eval-teamcreate-design.md`。
>
> **与 legacy 版本的关系**：`references/team-orchestration.md`（v2 prompt-driven）仍然可用，
> 是本文件的备选实现。两者**不混用**：一次回归要么全程 prompt-driven，要么全程 TeamCreate。
> 选择见下文「何时用 TeamCreate vs legacy」。

---

## 何时用 TeamCreate vs legacy

| 维度 | TeamCreate（本文） | legacy v2（team-orchestration.md） |
|------|---------------------|------------------------------------|
| 控制流 | TaskList 状态机 + blocks/blockedBy | Lead 的 prompt 记忆 + SendMessage |
| 跨会话恢复 | ✅ 任务目录持久化于 `~/.claude/tasks/rock-eval-team/` | ❌ 会话关闭需重起 |
| 长跑支持 | 后台 Agent + 可选 durable Cron | 后台 Agent + session-only Cron |
| 输出约束 | schema 强制结构化（见 §Schemas） | prompt「铁律」软约束 |
| 适用场景 | 全量长跑、需要恢复、多异常组并行诊断 | 单次会话内完成、快速试跑 |

**默认推荐**：全量回归（task 多、耗时长、大概率有失败需深挖）优先用 TeamCreate。
小规模验证（≤几个任务、单次会话可完成）仍走 legacy 或直接由 Lead 跑。

---

## 1. 实现范围

本文实现 **完整闭环**（Phase 1 → 4）：
- **Phase 1（task-1~task-4）**：确认参数 + oracle/nop 冒烟 + 汇总决策
- **Phase 2（Schema 定义）**：所有 9 个 schema 集中在 `references/schemas.json`
- **Phase 3（task-5/6/7）**：全量 run + 定时巡检 + 最终报告
- **Phase 4（task-8/9/10/11）**：并行诊断 + 调参决策 + Operator 执行 + 回 task-5 循环

具体已实现：
- **Team 入口**：Lead 通过 `TeamCreate` 创建 `rock-eval-team`
- **task-1 ~ task-11** 完整模板（task-1.5 对齐基线为可选扩展，不在本文主流程展开）
- **9 个 Schema**：`SmokeOutput` / `ConfigConfirmOutput` / `SmokeDecisionOutput` /
  `RunnerOutput` / `MonitorPatrolOutput` / `ReportOutput` / `DiagnoseOutput` /
  `TuningDecisionOutput` / `OperatorOutput`
- **CronCreate 巡检机制**：Monitor 的 session-only 定时巡检（task-6 内部）
- **后台 Agent 模式**：Runner / Monitor 用 `run_in_background: true` 长驻
- **调参循环**：task-11 完成后重置 task-5/task-6，最多 3 次循环

> **未在本文展开**：task-1.5（对齐基线确认，可选 Phase）。如果需要，由 Lead 在 task-2/task-3
> 完成后自行插建 task-1.5（参考 legacy `team-orchestration.md` 的 Phase 1.5 流程）。

---

## 2. Team 结构

### 2.1 创建 Team

```javascript
await TeamCreate({
  team_name: 'rock-eval-team',
  description: 'rock-eval 7 角色并行 pipeline 的 TeamCreate 实现',
  agent_type: 'general-purpose'   // team lead 类型
})
```

> **team_name 唯一性**：`~/.claude/tasks/rock-eval-team/` 是跨会话目录，多次回归会共用
> 同一 team。Lead 在创建 task 前应先 `TaskList` 检查是否已有残留 task；如有，按需清理或
> 在新 task 的 subject 上加 run 序号区分（例如「[run-2] oracle 冒烟」）。

### 2.2 Teammate 分配（完整 Phase 1-4）

| Teammate | 角色 | 职责 | 何时 spawn |
|----------|------|------|-----------|
| **lead**（你） | Lead | 纯协调：确认意图、初始化 task、汇总决策（task-1/4/10）、向用户转述 | 全程 |
| **smoke-oracle** | OracleChecker | oracle 冒烟，验证评分链（reward ≈ 满分） | task-2 |
| **smoke-nop** | NopChecker | nop 冒烟，验证环境/镜像/集群（reward ≈ 0） | task-3 |
| **runner** | Runner | 全量 run/retry/resume，后台长驻，里程碑回报 | task-5 |
| **monitor** | Monitor | 定时巡检（CronCreate）+ 最终报告 | task-6/task-7 |
| **diagnostician** | Diagnostician | 诊断异常组（并行 ≤2 实例） | task-8 / task-9 |
| **operator** | Operator | 停止 → 销毁 → 调参 → 准备重跑 | task-11 |

> Lead 按需 spawn：冒烟阶段只 spawn smoke-oracle + smoke-nop；进入 Phase 3 才 spawn
> runner + monitor；进入 Phase 4 才 spawn diagnostician(s) + operator。多个 diagnostician
> 实例用同一 name（`diagnostician`）的不同 spawn，由 TaskList 的 task id 区分。

---

## 3. 任务模板（task-1 ~ task-11）

### 3.1 任务依赖图（完整闭环）

```
task-1: 确认参数 + 是否冒烟  (lead)
   ├─ blocks → task-2, task-3
   │
task-2: oracle 冒烟  (smoke-oracle)        task-3: nop 冒烟  (smoke-nop)
   └─ blockedBy: task-1                     └─ blockedBy: task-1
   └─ blocks → task-4                       └─ blocks → task-4
              ↓                                       ↓
              └───────────────┬───────────────────────┘
                              ↓
                    task-4: 冒烟汇总决策  (lead)
                       └─ blockedBy: task-2, task-3
                       └─ blocks → task-5, task-6 (proceed)
                                  或 task-11       (operator)
                                  或 []            (abort)

─── Phase 3 ───────────────────────────────────────────────
task-5: 启动全量 run  (runner, 后台 Agent)    task-6: 启动巡检  (monitor, 后台 Agent + Cron)
   └─ blockedBy: task-4 (decision=proceed)       └─ blockedBy: task-4 (decision=proceed)
   └─ blocks → task-7                            └─ blocks → task-7
                ↓                                          ↓
                └──────────────────┬───────────────────────┘
                                   ↓
                         task-7: 生成最终报告  (monitor)
                            └─ blockedBy: task-5, task-6
                            └─ blocks → task-8, task-9

─── Phase 4 ───────────────────────────────────────────────
task-8: 诊断异常组 A  (diagnostician)          task-9: 诊断异常组 B  (diagnostician)
   └─ blockedBy: task-7                            └─ blockedBy: task-7
   └─ blocks → task-10                             └─ blocks → task-10
                ↓                                          ↓
                └──────────────────┬───────────────────────┘
                                   ↓
                         task-10: 调参决策  (lead)
                            └─ blockedBy: task-8, task-9
                            └─ blocks → task-11 (should_tune=true)
                                       或 []      (should_tune=false, 终止)

                         task-11: 执行调参  (operator)
                            └─ blockedBy: task-10
                            └─ 循环：完成后 Lead 重置 task-5 + task-6 状态为 pending，
                                      owner 清空，blockedBy 指向当前 task-11，触发新一轮 run
```

### 3.2 task-1：确认参数 + 是否冒烟（Lead）

| 字段 | 值 |
|------|-----|
| subject | `确认参数 + 是否冒烟` |
| owner | `lead`（由 team leader 自己执行） |
| blockedBy | `[]` |
| blocks | `["task-2", "task-3"]` |
| 输出 schema | `ConfigConfirmOutput`（见 `references/schemas.json`） |

**Lead 执行步骤**：

1. 与用户对话，确认以下内容（不要替用户做主）：
   - bench / dataset / split / agent（用 `rc agent run --help` 实时查可用值，不要硬编码）
   - `--window-size`（默认建议 10，遵守共享配额）
   - pass-through 参数：image / cluster / model / namespace / cpus / memory / ee / set /
     config / pre/no-pre / async-mode / user-id / base-url / api-key 等。**只传用户明确指定的**
   - 是否冒烟（默认建议冒烟；用户明确拒绝才设 `smoke=false`）
   - 是否对齐已知分数（默认否；是则 Phase 1.5 会创建 baseline，本文主流程不展开，见 §3.9 末尾的 alignment 变体说明）
2. 如果用户只给了 bench 名，按 SKILL.md §1「Resolving the task list」解析 dataset/split。
3. 选 2-3 个代表性 task 作为 smoke_tasks（跨难度/文件大小）。
4. 构造 `ConfigConfirmOutput` 对象（必须通过 schema 校验）。
5. `TaskUpdate` 把 schema 输出写入 task-1 的 `metadata.output`，并将 task-1 标记 `completed`。
   完成 task-1 会自动解除 task-2 / task-3 的 blockedBy。

**关键约束（Lead 零执行铁律，与 legacy 一致）**：
- 不直接跑 `regression.py` / `rc`
- 不读 `results/*.json` / `logs/` / `configs/`
- 不拼命令行参数字符串（参数对象由 schema 结构化持有，由 teammate 自己拼成 CLI）

### 3.3 task-2：oracle 冒烟（smoke-oracle）

| 字段 | 值 |
|------|-----|
| subject | `oracle 冒烟` |
| owner | `smoke-oracle` |
| blockedBy | `["task-1"]` |
| blocks | `["task-4"]` |
| 输出 schema | `SmokeOutput` |

**smoke-oracle Teammate Prompt 模板**（Lead 通过 Agent tool spawn，传 schema）：

```
你是 rock-eval-team 的 smoke-oracle。task-1 已完成，配置已确认。
你的任务：用 oracle agent 跑 2-3 个代表 task，验证评分链是否正常。

【配置】(来自 task-1 的 ConfigConfirmOutput)
  bench: <BENCH>
  dataset: <DATASET>
  split: <SPLIT>
  smoke_tasks: <TASK_ID_1>, <TASK_ID_2>, <TASK_ID_3>
  pass_through: <对象，原样转发到 --flag value>

【执行】
  python3 <regression.py 绝对路径> run \
    --bench <BENCH> --dataset <DATASET> --split <SPLIT> \
    --agent oracle \
    --tasks <TASK_ID_1>,<TASK_ID_2>,<TASK_ID_3> \
    --window-size 2 \
    <pass_through 转 CLI flags>

  完成后跑 report 查看 reward：
  python3 <regression.py 绝对路径> report <EXP_ID> --format json

【你的输出】必须符合 SmokeOutput schema：
  - experiment_id: run 返回的具体 id
  - ok: true 当且仅当所有 smoke task reward ≈ 满分（评分链正常）
  - detail: 仅 ok=false 时填，一句话说明哪个 task reward 异常、实际值

【禁止】
  - 贴日志原文、trajectory、HTML 全文
  - 自行决定进入 Phase 2（那是 lead 的 task-4 职责）
  - 读取其他 task 的实验结果

完成后调用 TaskUpdate 把 SmokeOutput 写入本 task 的 metadata.output，
并将 task-2 标记 completed。
```

### 3.4 task-3：nop 冒烟（smoke-nop）

| 字段 | 值 |
|------|-----|
| subject | `nop 冒烟` |
| owner | `smoke-nop` |
| blockedBy | `["task-1"]` |
| blocks | `["task-4"]` |
| 输出 schema | `SmokeOutput` |

**smoke-nop Teammate Prompt 模板**（与 smoke-oracle 同构，差异如下）：

```
你是 rock-eval-team 的 smoke-nop。task-1 已完成，配置已确认。
你的任务：用 nop agent 跑 2-3 个代表 task，验证环境/镜像/集群是否正常。

【配置】同 task-1 的 ConfigConfirmOutput（与 smoke-oracle 一致）。

【执行】
  python3 <regression.py 绝对路径> run \
    --bench <BENCH> --dataset <DATASET> --split <SPLIT> \
    --agent nop \
    --tasks <TASK_ID_1>,<TASK_ID_2>,<TASK_ID_3> \
    --window-size 2 \
    <pass_through 转 CLI flags>

  完成后跑 report 查看状态：
  python3 <regression.py 绝对路径> report <EXP_ID> --format json

【你的输出】必须符合 SmokeOutput schema：
  - experiment_id: run 返回的具体 id
  - ok: true 当且仅当所有 smoke task 正常完成且 reward ≈ 0（环境正常）
  - detail: 仅 ok=false 时填，一句话说明哪个 task 失败、异常类型

【禁止】同 smoke-oracle。
```

### 3.5 task-4：冒烟汇总决策（Lead）

| 字段 | 值 |
|------|-----|
| subject | `冒烟汇总决策` |
| owner | `lead` |
| blockedBy | `["task-2", "task-3"]` |
| blocks | decision=proceed → `["task-5", "task-6"]`；decision=operator → `["task-11"]`；decision=abort → `[]` |
| 输出 schema | `SmokeDecisionOutput` |

**Lead 执行步骤**：

1. 等 task-2 和 task-3 都 completed（TaskList 查询确认）。
2. 读取两者的 `metadata.output`（都是 `SmokeOutput` 对象）。
3. 按下表决策（产出 `SmokeDecisionOutput.decision`）：

   | oracle_ok | nop_ok | decision | 后续路由 |
   |-----------|--------|----------|---------|
   | true | true | `proceed` | 解除 task-5（全量 run）+ task-6（巡检）阻塞 |
   | false | true | `operator` | 评分链问题，通常非环境。解除 task-11（调参）或向用户报告 |
   | true | false | `operator` | 环境/镜像/集群问题，多半可调参修复。解除 task-11 |
   | false | false | `operator` 或 `abort` | 两者都挂。若像配置错误 → `operator`；若是集群不可达等硬故障 → `abort` |

4. 写 `tuning_hint`（decision=operator 时必填）：基于 SmokeOutput.detail 给出
   具体调参建议（例如 `--memory 8Gi --poll-timeout 900`）。
5. 把 `SmokeDecisionOutput` 写入 task-4 的 `metadata.output`，标记 task-4 completed。
6. 按 `decision` 路由：`proceed` → 用 `addBlocks: ["task-5", "task-6"]` 释放下游（§3.6 起）；
   `operator` → 用 `addBlocks: ["task-11"]` 直接走调参；`abort` → 不释放任何下游，run 终止。
7. 向用户转述决策与原因（保持 Lead 与用户沟通的职责）。

---

### 3.6 task-5：启动全量 run（runner，后台 Agent）

| 字段 | 值 |
|------|-----|
| subject | `启动全量 run` |
| owner | `runner` |
| blockedBy | `["task-4"]`（仅 decision=proceed 才被解除） |
| blocks | `["task-7"]` |
| 输出 schema | `RunnerOutput` |
| 执行模式 | **后台 Agent**：Lead 用 `Agent({ run_in_background: true })` spawn，runner 长驻 |

> **循环复用**：task-11 完成后 Lead 会把 task-5 重置为 pending、清空 owner，重新派发 runner
> 跑调参后的新配置。每轮循环 task-5 的 subject 可加 run 序号区分，例如
> `[run-2] 启动全量 run`，但 task id 保持 task-5（保留 blocks/blockedBy 拓扑）。

**runner Teammate Prompt 模板**（Lead 通过 Agent tool spawn，填入 task-1 的 ConfigConfirmOutput
或上一轮 task-11 的 OperatorOutput.new_pass_through）：

```
你是 rock-eval-team 的 runner（task-5）。task-4 已决策 proceed，配置已确认。
你的任务：后台执行全量回归，按里程碑回报，不诊断、不读 task 日志原文。

【配置】
  bench: <BENCH>
  dataset: <DATASET>
  split: <SPLIT>
  agent: <AGENT>   // 注意是真实 agent，不是 oracle/nop
  window_size: <N>  // 通常 10，遵守共享配额
  pass_through: <对象，原样转发到 --flag value>

【执行】
  python3 <regression.py 绝对路径> run \
    --bench <BENCH> --dataset <DATASET> --split <SPLIT> \
    --agent <AGENT> --window-size <N> \
    <pass_through 转 CLI flags>

  并轮询直到所有 task 进入 success / error 状态（卡住超时另说）。

【里程碑回报】通过 SendMessage 给 lead，不要在 prompt 里展开：
  - 派发完成：给出 experiment_id（实际返回值，不要抓「最新文件」）
  - 每约 25% 进度：成功/失败/分发计数
  - 全部结束：experiment_id + 一句话状态
  - 卡住/超时：说明卡在哪（哪个 task、什么状态、卡了多久）

【最终输出】必须符合 RunnerOutput schema（写入 task-5.metadata.output）：
  - experiment_id: run 返回的具体 id
  - status: done / stuck / interrupted
  - success / error / dispatched / total: 最终计数
  - stuck_reason: 仅 status=stuck 时填

【禁止】
  - 贴单个 task 的日志或 rc 原始输出（只给计数与状态）
  - 自行决定 retry / 调参（那是 task-10 / task-11 的职责）
  - 读其他 task 的实验结果
  - 自行生成 HTML 报告（那是 task-7 monitor 的职责）

完成后调用 TaskUpdate 把 RunnerOutput 写入本 task 的 metadata.output，
并将 task-5 标记 completed。这会解除 task-7 的 blockedBy 之一。
```

> **后台与里程碑解耦**：runner 后台 spawn 后立即返回 control 给 Lead。里程碑回报通过
> `SendMessage` 异步推送（schema 不强制，自然语言一行即可）；最终 `RunnerOutput` 走
> TaskUpdate 在 task-5 completed 时写入。Lead 不阻塞等 runner，可以并行处理其他事。

### 3.7 task-6：启动巡检（monitor，后台 Agent + CronCreate）

| 字段 | 值 |
|------|-----|
| subject | `启动巡检` |
| owner | `monitor` |
| blockedBy | `["task-4"]`（仅 decision=proceed 才被解除） |
| blocks | `["task-7"]` |
| 输出 schema | `MonitorPatrolOutput` |
| 执行模式 | **后台 Agent + CronCreate**：monitor 一启动就 `CronCreate` 每 3 分钟触发巡检 |

> **与 legacy 的对齐**：legacy v2 的巡检判据有 4 条（dispatched 不降、error 堆积、
> pass rate 异常、task 停留超时）。TeamCreate 版本**简化为 2 条**，降低复杂度：
> ① dispatched 连续 ≥3 次不下降；② error 堆积（>总数 10% 或连续增长）。
> pass rate 与单 task 超时判据在 TeamCreate 版本中**移除**（pass rate 留给 task-10 决策，
> 单 task 超时由 runner 自己的里程碑回报兜住），避免巡检逻辑过于复杂。

**monitor Teammate Prompt 模板**：

```
你是 rock-eval-team 的 monitor（task-6 + task-7）。task-4 已决策 proceed，
runner 已启动全量 run（experiment_id 见 task-5.metadata 或 SendMessage 通知）。

【阶段一：巡检模式（task-6）】
  立即用 CronCreate 起一个定时巡检（session-only，每 3 分钟一次）：
    CronCreate({
      cron: '*/3 * * * *',
      recurring: true,
      durable: false,
      prompt: '<下面的巡检子 prompt>'
    })

  巡检子 prompt（每次 cron 触发都执行一遍）：
    1. 先 sync 拉远端真实进展：
       python3 <regression.py 绝对路径> sync <EXP_ID>
    2. 再汇总：
       python3 <regression.py 绝对路径> report <EXP_ID> --format json
       记录本次 total / success / error / dispatched
    3. 读写巡检状态文件 logs/<EXP_ID>/monitor-state.json：
       - 读上次快照，更新 no_decrease_streak、error_history
       - 写本次快照
       （结构：last_dispatched_count / no_decrease_streak / error_history: [...]/  *不维护 tasks 字段，因为判据④已移除*）
    4. 判可疑（满足任一即视为可疑，简化判据）：
       ① dispatched 数量连续 ≥3 次巡检不下降（no_decrease_streak ≥ 3）
          no_decrease_streak 维护算法：dispatched 上升则 +1，下降则清零，相等则不变
       ② error 数 > 总数 10% 或连续 ≥3 次增长（看 error_history）
    5. 若判定可疑 → 对该 job 调用 rock-agent-debug 深挖（确认进展，非根因诊断）：
       提供 experiment_id + job_name，让其拉 trial 级真实状态
    6. SendMessage 给 lead 一行：状态=正常/可疑 + 当前数字；
       可疑时附 rock-agent-debug 给出的一句话

  no_decrease_streak 维护算法（精确定义，避免 agent 自由发挥）：
    - 新 run 第一次巡检或状态文件不存在 → no_decrease_streak = 0，记录基线
    - dispatched < last_dispatched_count → 清零
    - dispatched == last_dispatched_count → 保持不变（不累计）
    - dispatched > last_dispatched_count → no_decrease_streak += 1
    - 每次巡检后用本次 dispatched 覆盖 last_dispatched_count

  监听 runner 完成（task-5 status=completed 或 SendMessage 通知）：
    → 进入阶段二（task-7）

【阶段二：最终报告（task-7）】见 §3.8 的 task-7 prompt。

【task-6 最终输出】必须符合 MonitorPatrolOutput schema（写入 task-6.metadata.output）：
  - experiment_id
  - verdict: normal / suspicious（聚合整个巡检期间的最终判据）
  - patrol_count: 巡检次数
  - final_dispatched / final_error: 最后一次快照的计数
  - no_decrease_streak: 最终 streak 值
  - sample_message: verdict=suspicious 时必填（rock-agent-debug 一句话）

完成后 TaskUpdate 标记 task-6 completed，解除 task-7 的 blockedBy 之一。

【禁止】
  - 贴 HTML 全文、任务明细表
  - 做根因诊断（深挖只确认「是否假执行」，根因归 task-8/9 diagnostician）
  - 自行调参或 retry
```

> **Cron 与 Agent 的关系**：monitor 是后台 Agent（长驻），但巡检的「每 3 分钟触发一次」
> 由 CronCreate 实现（不是 monitor 自己 sleep）。Cron 是 session-only，会话关闭即停止；
> 长跑需跨会话巡检时改用 `durable: true`（写 `.claude/scheduled_tasks.json`）。

### 3.8 task-7：生成最终报告（monitor）

| 字段 | 值 |
|------|-----|
| subject | `生成最终报告` |
| owner | `monitor`（与 task-6 同一个 teammate） |
| blockedBy | `["task-5", "task-6"]` |
| blocks | `["task-8", "task-9"]` |
| 输出 schema | `ReportOutput` |

**monitor 在 task-7 阶段的执行步骤**（接续 §3.7 的阶段二）：

1. 等 task-5（runner）和 task-6（巡检）都 completed。
2. `CronDelete` 清理巡检 Cron，避免空跑。
3. 若 run 被中断过，先 sync：`python3 <regression.py 绝对路径> sync <EXP_ID>`。
4. 生成 HTML：`python3 <regression.py 绝对路径> report <EXP_ID> --format html`。
5. 汇总 report JSON：total / success / error / dispatched / pass_rate / exception_groups。
6. 构造 `ReportOutput`（写入 task-7.metadata.output）：
   - `exception_groups`：按计数降序取 Top 组（用于 Lead 派 diagnostician）
   - `html_path`：绝对路径
7. `TaskUpdate` 标记 task-7 completed，解除 task-8 / task-9 的 blockedBy。
8. SendMessage 给 lead：一句话摘要 + exception_groups 的 Top 类型。

> **task-7 不做诊断**：ReportOutput 只列异常组的 type/count/sample_message，根因留待
> task-8/9 的 Diagnostician。Monitor 在 task-7 阶段已经"卸任"，后续不再 spawn。

### 3.9 task-8 / task-9：诊断异常组（diagnostician，并行 ≤2）

| 字段 | 值（task-8） | 值（task-9） |
|------|--------------|--------------|
| subject | `诊断异常组 <TYPE_A>` | `诊断异常组 <TYPE_B>` |
| owner | `diagnostician` | `diagnostician` |
| blockedBy | `["task-7"]` | `["task-7"]` |
| blocks | `["task-10"]` | `["task-10"]` |
| 输出 schema | `DiagnoseOutput` | `DiagnoseOutput` |

**并行约束（≤2 实例）**：
- ReportOutput.exception_groups ≤2 个 → 全部并行（task-8 + task-9）
- exception_groups >2 个 → 按计数降序取 Top-2 先挖（task-8 + task-9），挖完 Lead 视情况
  在 task-10 决策后追加 task-8.1 / task-9.1
- 用户明确要求加速时，可放宽到 3-4 个（注意 ROCKCLI 配额，由 Lead 向用户确认）

**diagnostician Teammate Prompt 模板**（Lead 用 TYPE_A / TYPE_B / 代表 task id 填入）：

```
你是 rock-eval-team 的 diagnostician（task-8 或 task-9）。task-7 报告已完成。
你的任务：深挖 experiment <EXP_ID> 中异常组【<EXCEPTION_TYPE>】的根因。

【输入】
  experiment_id: <EXP_ID>  // 来自 task-7 的 ReportOutput.experiment_id
  exception_type: <EXCEPTION_TYPE>  // 来自 ReportOutput.exception_groups[].type
  代表 task: <TASK_ID>  // 来自 ReportOutput.exception_groups[].sample_message 推断，或 Lead 选定
  // 你只诊断这一个组，其他组由另一个 diagnostician 实例处理

【执行】
  python3 <regression.py 绝对路径> diagnose <EXP_ID> --task <TASK_ID> \
    --remote --trajectory --artifacts

【你的输出】必须符合 DiagnoseOutput schema（写入 task-8 / task-9.metadata.output）：
  - root_cause: 一句话根因。证据不足时填「证据不足，建议挖 <另一个 task id>」
  - exception_type: 你诊断的组的 type（与输入一致）
  - tasks: 你实际诊断的 + 推断共享根因的 task id 列表
  - is_param_issue: 是否可调参修复（memory/cpus/poll-timeout/image/cluster/model/agent/namespace/ee）
  - suggestion: 具体建议。is_param_issue=true 时必须点名要改的 param 和建议值

【铁律（违反即失败）】
  1. trajectory / 远端日志 / artifacts 原文留在你自己的上下文，绝不贴回给 lead
  2. 只回 DiagnoseOutput 对象，不展开自然语言结论
  3. 挖到根因可定论即止，不展开挖所有失败任务
  4. 挖不出根因，如实回「证据不足」

完成后 TaskUpdate 标记 task-8 / task-9 completed，解除 task-10 的 blockedBy 之一。
```

> **alignment 模式变体**：若 task-1 配置了 `alignment=true`，Lead 在 task-7 后追加一个
> `task-7.5: alignment 对比诊断`（同样 schema），对比 actual vs expected reward。
> 此变体 prompt 见 legacy `team-orchestration.md` 的「Diagnostician（alignment 对比模式）」。

### 3.10 task-10：调参决策（lead）

| 字段 | 值 |
|------|-----|
| subject | `调参决策` |
| owner | `lead` |
| blockedBy | `["task-8", "task-9"]` |
| blocks | should_tune=true → `["task-11"]`；should_tune=false → `[]`（终止） |
| 输出 schema | `TuningDecisionOutput` |

**Lead 执行步骤**：

1. 等 task-8 和 task-9 都 completed。
2. 读两者的 `metadata.output`（都是 `DiagnoseOutput`）。
3. 读上一轮 task-10 的 `metadata.output.loop_count`（首轮 loop_count=0）。
4. 按 **循环终止策略** 决策：

   | 条件 | should_tune | reason |
   |------|-------------|--------|
   | loop_count ≥ 3 | false | 连续 3 次调参未改善，停止（避免死循环） |
   | 所有 DiagnoseOutput.is_param_issue=false | false | 无参数问题，停止 |
   | 至少一个 is_param_issue=true 且 loop_count<3 | true | 进入 Operator |
   | 用户明确叫停 | false | 用户主动终止 |

5. 决定 `risk_level`：
   - 只涉及 memory/cpus/poll-timeout/ee → `low`
   - 涉及 image/cluster/model/agent/namespace → `high`（需 Lead → 用户确认）
6. 构造 `tuning_params`（should_tune=true 时必填）：合并各 DiagnoseOutput.suggestion 的具体 param。
7. 构造 `TuningDecisionOutput`，写入 task-10.metadata.output。
8. 路由：
   - should_tune=true → `addBlocks: ["task-11"]`，派 operator
   - should_tune=false → 向用户报告循环终止，run 结束

> **高风险路径**：risk_level=high 时，Lead 在派 operator 前必须向用户确认（不替用户做主）。
> 用户拒绝 → 把 should_tune 改回 false，重新 TaskUpdate。

### 3.11 task-11：执行调参（operator）

| 字段 | 值 |
|------|-----|
| subject | `执行调参` |
| owner | `operator` |
| blockedBy | `["task-10"]` |
| blocks | `[]`（不直接 blocks task-5；循环由 Lead 重置 task-5 状态触发，见 §3.12） |
| 输出 schema | `OperatorOutput` |

> **循环机制说明**：task-11 完成后，**不是**靠 `blocks` 自动触发 task-5（blocks 是单向的，
> 已 completed 的 task 不能再 block 新任务）。循环靠 Lead 显式重置 task-5/task-6 状态实现，
> 详见 §3.12。

**operator Teammate Prompt 模板**：

```
你是 rock-eval-team 的 operator（task-11）。task-10 已决策 should_tune=true。
你的任务：执行 停止 → 销毁 → 调参 → 准备重跑 的闭环。

【输入】
  原 experiment_id: <EXP_ID>  // 来自 task-7 的 ReportOutput.experiment_id
  原 pass_through: <对象>  // 来自 task-1 的 ConfigConfirmOutput.pass_through 或上一轮 task-11
  tuning_params: <对象>  // 来自 task-10 的 TuningDecisionOutput.tuning_params
  risk_level: <low / high>

【执行流程】
  1. 判断风险等级：
     - low（memory/cpus/poll-timeout/ee）→ 直接执行，事后通知 lead
     - high（image/cluster/model/agent/namespace）→ SendMessage 给 lead 汇报建议，
       等 lead 转用户确认后下发

  2. 停止当前实验的未完成任务（如有）：
     rc agent view -e <EXP_ID> 查看在跑任务 → 逐个 rc sandbox destroy <SANDBOX_ID>

  3. 批量停止该实验下所有沙箱（一次性覆盖 RUNNING/PENDING，含未记录在 results JSON 里的）：
     rc expr <EXP_ID> sandboxes stop -y --concurrency 10
     （高风险变更可先 --dry-run 预览影响范围，再报 Lead 确认）

  4. 销毁相关沙箱：
     从 results JSON 提取 sandbox_id → rc sandbox destroy <SANDBOX_ID>

  5. 合并新 pass_through = { ...原 pass_through, ...tuning_params }

  6. （不自行派 runner 重跑 —— 那是 lead 在循环重置后派 task-5 的职责）

【你的输出】必须符合 OperatorOutput schema（写入 task-11.metadata.output）：
  - action_taken: executed_low_risk / pending_high_risk_confirmation / skipped_no_action
  - new_experiment_id: 通常 null（新 id 由下一轮 runner 产生）
  - new_pass_through: 合并后的 pass_through 对象（action_taken=executed_low_risk 时必填）
  - detail: 一句话总结

【禁止】
  - 自行派 runner 重跑（那是 lead 在循环重置后的职责）
  - 自行决定高风险调参（必须等 lead 转用户确认）

完成后 TaskUpdate 标记 task-11 completed，并 SendMessage 通知 lead「调参已就绪，
请重置 task-5/task-6 启动新一轮」。
```

### 3.12 调参循环：task-11 → task-5/task-6 的重置流程

task-11 completed 后，Lead 执行循环重置（**这是显式操作，不是 blocks 自动触发**）：

```javascript
// 1. 读 task-11 的 OperatorOutput
const operatorOut = <task-11.metadata.output>

if (operatorOut.action_taken === 'pending_high_risk_confirmation') {
  // 等用户确认后再继续；用户拒绝则终止循环
}

// 2. 重置 task-5（全量 run）
await TaskUpdate({
  taskId: 'task-5',
  status: 'pending',           // 从 completed 回到 pending
  owner: '',                   // 清空 owner，让新 runner 认领
  // 不动 blockedBy：task-5 的 blockedBy 本来就是 [task-4]，task-4 仍 completed
  // 关键：在 metadata 里写入 new_pass_through 和 new subject
  metadata: {
    output: null,              // 清空上一轮 RunnerOutput
    new_pass_through: operatorOut.new_pass_through,
    run_round: <loop_count + 1>  // 用于区分轮次
  }
})
await TaskUpdate({
  taskId: 'task-5',
  subject: `[run-${round}] 启动全量 run`   // 加序号区分
})

// 3. 同样重置 task-6（巡检）
await TaskUpdate({
  taskId: 'task-6',
  status: 'pending',
  owner: '',
  metadata: { output: null, run_round: <loop_count + 1> }
})

// 4. 重置 task-7（报告）—— 也要重置，否则它已 completed 不会重跑
await TaskUpdate({
  taskId: 'task-7',
  status: 'pending',
  owner: '',
  metadata: { output: null }
})

// 5. 重新派 runner + monitor（与首次派发同构，prompt 用 new_pass_through）
//    task-8/9/10/11 不重置 —— 它们会自然被新一轮 task-7 完成后重新触发
//    （因为它们 blockedBy task-7，task-7 回到 pending 后它们的 blockedBy 又生效了）
```

> **task-8/9/10/11 不需要显式重置**：它们的 blockedBy 是 `[task-7]` / `[task-8,task-9]` /
> `[task-10]`。当 task-7 从 completed 回到 pending，这些下游 task 的 blockedBy 自动重新生效
> （CC 的 TaskList 会重新检查依赖）。但它们上一轮的 `metadata.output` 会留着，新一轮完成时
> 会被覆盖，不影响正确性。如果担心混淆，Lead 可在新轮开始时清空这些 task 的 metadata.output。

> **循环终止**：当 task-10 的 `TuningDecisionOutput.should_tune=false` 时，不再派 task-11，
> 循环终止。Lead 向用户报告最终结论（pass_rate、调参历史、剩余异常）。

---

## 4. Schemas

所有 schema 定义集中在 **`references/schemas.json`**，使用 JSON Schema draft 2020-12。
Teammate 通过 Agent tool 的 schema 选项强制结构化输出。

### 4.1 已定义 schema

| Schema | 用于 task | 产生者 | 必填字段 |
|--------|----------|--------|---------|
| `ConfigConfirmOutput` | task-1 | lead | bench, agent, smoke |
| `SmokeOutput` | task-2, task-3 | smoke-oracle / smoke-nop | experiment_id, ok |
| `SmokeDecisionOutput` | task-4 | lead | decision, oracle_ok, nop_ok |
| `RunnerOutput` | task-5 | runner | experiment_id, status, success, error, dispatched, total |
| `MonitorPatrolOutput` | task-6 | monitor | experiment_id, verdict, patrol_count, final_dispatched, final_error |
| `ReportOutput` | task-7 | monitor | experiment_id, total, success, error, dispatched, pass_rate, html_path, exception_groups |
| `DiagnoseOutput` | task-8, task-9 | diagnostician | root_cause, exception_type, tasks, is_param_issue, suggestion |
| `TuningDecisionOutput` | task-10 | lead | should_tune, risk_level, reason, loop_count |
| `OperatorOutput` | task-11 | operator | action_taken, detail |

### 4.2 关键字段说明

**SmokeOutput**
- `experiment_id`：smoke run 返回的具体 id，必须由 run 命令实际返回，禁止让 teammate
  自己抓「最新文件」。
- `ok`：通过条件的语义随角色不同（OracleChecker 看 reward≈满分，NopChecker 看 reward≈0
  且正常完成），由 prompt 内的判据明确。
- `detail`：仅在 `ok=false` 时必填，一句话，禁止贴原文。

**ConfigConfirmOutput**
- `pass_through`：键为 flag 名（去掉 `--`），值为字符串。布尔 flag 用 `"true"`。
  只包含用户明确指定的 flag，不注入默认值。
- `smoke_tasks`：smoke=true 时必填，2-3 个代表性 task id。
- `alignment`：是否对齐已知分数（Phase 1.5 入口标志）。

**SmokeDecisionOutput**
- `decision` 枚举 `proceed` / `operator` / `abort`，驱动后续 task 的 unblock 路由。
- `tuning_hint`：decision=operator 时必填，给 Operator 的具体调参建议。

**RunnerOutput**
- `status`：`done` / `stuck` / `interrupted`。`stuck` 必填 `stuck_reason`，是 task-10
  决策是否调参的重要输入。
- `experiment_id`：必须来自 run 命令实际返回，禁止「最新文件」推断。

**MonitorPatrolOutput**
- `verdict`：`normal` / `suspicious`。判据简化为 2 条（见 §3.7）：dispatched 不降 streak ≥3
  或 error 堆积。`verdict=suspicious` 必填 `sample_message`（rock-agent-debug 一句话）。
- `patrol_count`：巡检次数，0 表示 run 在首次 cron 触发前就结束了。

**ReportOutput**
- `exception_groups`：按计数降序的异常组，每项含 type/count/sample_message。Lead 据此派
  diagnostician（≤2 并行），所以 Top-2 决定了 task-8/task-9 诊断什么。
- `html_path`：绝对路径，不贴 HTML 内容。

**DiagnoseOutput**
- `is_param_issue`：是否可调参修复，决定 task-10 是否进入 task-11。所有 is_param_issue=false
  则循环终止。
- `suggestion`：is_param_issue=true 时必须点名具体 param 和建议值（例如 `--memory 8Gi`）。

**TuningDecisionOutput**
- `should_tune` + `loop_count`：循环终止策略的核心。loop_count ≥3 或无 param issue 时
  should_tune=false。
- `risk_level`：`low`（operator 自主）/ `high`（需 Lead → 用户确认）/ `none`（不调参）。

**OperatorOutput**
- `action_taken`：`executed_low_risk` / `pending_high_risk_confirmation` / `skipped_no_action`。
- `new_pass_through`：合并后的新参数，Lead 在循环重置时读它构造新一轮 runner prompt。
  Operator **不**自行派 runner，只准备配置。

### 4.3 使用方式（Agent tool with schema）

```javascript
// Lead 派 smoke-oracle 执行 task-2
const smokeOracleResult = await Agent({
  description: 'oracle 冒烟验证评分链',
  prompt: '<task-2 prompt 模板，填入 task-1 的 ConfigConfirmOutput 字段>',
  schema: SMOKE_OUTPUT_SCHEMA,   // 从 schemas.json 加载 definitions.SmokeOutput
  name: 'smoke-oracle',
  team_name: 'rock-eval-team',
  run_in_background: true
})
// Agent 自动调用 StructuredOutput tool，返回符合 SmokeOutput 的对象
```

---

## 5. Lead 操作 Runbook（完整端到端）

> **可直接照着执行**。每一步都给出具体 API 调用。

### Step 0 — 判断是否启用 TeamCreate

读 §「何时用 TeamCreate vs legacy」。决定用 TeamCreate 才继续。

### Step 1 — 创建 Team + 初始化任务列表

```javascript
// 1.1 创建 team
await TeamCreate({
  team_name: 'rock-eval-team',
  description: 'rock-eval 7 角色并行 pipeline',
  agent_type: 'general-purpose'
})

// 1.2 检查残留 task（跨会话恢复时）
const existing = await TaskList()
if (existing.some(t => t.status !== 'completed')) {
  // 有未完成 task，向用户确认：继续恢复 or 清理重开
}

// 1.3 创建 task-1（只建 task-1，下游 task 等 task-1 完成后再建，
//     避免过早创建一堆被阻塞的 task）
const task1 = await TaskCreate({
  subject: '确认参数 + 是否冒烟',
  description: 'Lead 与用户确认 bench/dataset/split/agent/pass-through，产出 ConfigConfirmOutput',
  activeForm: '确认 run 配置'
})
```

### Step 2 — 执行 task-1（Lead 自己）

按 §3.2 与用户对话，产出 `ConfigConfirmOutput`。

```javascript
await TaskUpdate({
  taskId: task1.id,
  owner: 'lead',
  status: 'in_progress'
})
// ... 与用户对话、解析 dataset/split、选 smoke_tasks ...
await TaskUpdate({
  taskId: task1.id,
  status: 'completed',
  metadata: { output: <ConfigConfirmOutput 对象> },
  addBlocks: []   // task-2/task-3 的 blockedBy 在创建时指定，不用这里 addBlocks
})
```

### Step 3 — 创建并派发 task-2 / task-3（并行）

```javascript
const cfg = <task-1 的 ConfigConfirmOutput>

const task2 = await TaskCreate({
  subject: 'oracle 冒烟',
  description: 'smoke-oracle 验证评分链，产出 SmokeOutput',
  activeForm: '执行 oracle 冒烟',
  addBlockedBy: [task1.id]
})
const task3 = await TaskCreate({
  subject: 'nop 冒烟',
  description: 'smoke-nop 验证环境/镜像/集群，产出 SmokeOutput',
  activeForm: '执行 nop 冒烟',
  addBlockedBy: [task1.id]
})

// 并行 spawn 两个 teammate（Agent tool with schema）
const [oracleOut, nopOut] = await Promise.all([
  Agent({
    description: 'oracle 冒烟',
    prompt: renderSmokePrompt('oracle', cfg, task2.id),
    schema: SMOKE_OUTPUT_SCHEMA,
    name: 'smoke-oracle',
    team_name: 'rock-eval-team',
    run_in_background: true
  }),
  Agent({
    description: 'nop 冒烟',
    prompt: renderSmokePrompt('nop', cfg, task3.id),
    schema: SMOKE_OUTPUT_SCHEMA,
    name: 'smoke-nop',
    team_name: 'rock-eval-team',
    run_in_background: true
  })
])
```

> teammate 收到 prompt 后，自己 `TaskUpdate` 认领并完成；上面 `Promise.all` 也可换成
> 事件驱动（teammate 完成后 SendMessage 通知 lead）。两种都行，按团队习惯选。

### Step 4 — 汇总决策（task-4）

```javascript
const task4 = await TaskCreate({
  subject: '冒烟汇总决策',
  description: 'Lead 聚合 task-2/task-3 的 SmokeOutput，产出 SmokeDecisionOutput',
  activeForm: '汇总冒烟决策',
  addBlockedBy: [task2.id, task3.id]
})

// 等 task-2/task-3 completed 后
await TaskUpdate({ taskId: task4.id, owner: 'lead', status: 'in_progress' })

const oracleSmoke = <task-2.metadata.output>   // SmokeOutput
const nopSmoke = <task-3.metadata.output>       // SmokeOutput

// 按 §3.5 决策表
const decision = decideSmoke(oracleSmoke.ok, nopSmoke.ok, oracleSmoke.detail, nopSmoke.detail)

// 注意时序：先创建下游 task（pending + blockedBy task-4），再用 addBlocks 完成 task-4 解除阻塞
let unblockIds = []
if (decision.decision === 'proceed') {
  // 提前创建 task-5/6/7（仍被 task-4 阻塞），下一步 Step 5 会派发 runner/monitor
  // 这里只建 task，不 spawn agent；spawn 在 Step 5
  // 见 Step 5 的实现（task5/task6/task7 在那里创建）
  // 为保持时序清晰，Step 5 会先 TaskCreate 再回来完成 task-4
} else if (decision.decision === 'operator') {
  // 直接跳 Step 8 创建 task-11
}

// 向用户转述 decision 与原因（Lead 与用户沟通职责，不替用户做主）
```

> **路由分支**：
> - `proceed` → Step 5（创建 task-5/6/7，再完成 task-4 解除阻塞，进入全量 run）
> - `operator` → **冒烟失败快捷路径**：直接创建 task-11（不创建 task-5/6/7/8/9/10），
>   用冒烟的 experiment_id（task-2 或 task-3 的 SmokeOutput.experiment_id）作为
>   operator 的输入。完成 task-4 时 `addBlocks: [task11.id]`。operator 执行后，若
>   `OperatorOutput.action_taken=executed_low_risk`，直接回到 Step 5 创建 task-5/6/7
>   开始首次全量 run（new_pass_through 用 operator 的输出）。这条路径**不经过** Step 6/7/8
>   的诊断循环，因为冒烟阶段就已定位是参数问题。
> - `abort` → 完成 task-4 不 addBlocks，向用户报告终止原因，run 结束
>
> **时序约定**：task-4 的 `addBlocks` 在下游 task 创建之后再调用（即 Step 5 创建完 task-5/6
> 后，或 operator 路径创建完 task-11 后，回头 `TaskUpdate(task4, status=completed, addBlocks=[...])`）。
> 这样避免引用尚未创建的 task id。

### Step 5 — Phase 3 启动：创建 task-5 / task-6 / task-7（仅 decision=proceed）

```javascript
// task-4 的 SmokeDecisionOutput.decision === 'proceed' 才走这里
// 'operator' 直接跳到 Step 8（创建 task-11）；'abort' 直接终止

const task5 = await TaskCreate({
  subject: '启动全量 run',
  description: 'runner 后台执行全量 run，产出 RunnerOutput',
  activeForm: '执行全量 run',
  addBlockedBy: [task4.id]
})
const task6 = await TaskCreate({
  subject: '启动巡检',
  description: 'monitor 启动 CronCreate 巡检，产出 MonitorPatrolOutput',
  activeForm: '执行定时巡检',
  addBlockedBy: [task4.id]
})
const task7 = await TaskCreate({
  subject: '生成最终报告',
  description: 'monitor 生成 ReportOutput（HTML + 异常分组）',
  activeForm: '生成最终报告',
  addBlockedBy: [task5.id, task6.id]
})

// 下游 task 已创建，现在完成 task-4 解除 task-5/task-6 的阻塞
await TaskUpdate({
  taskId: task4.id,
  status: 'completed',
  metadata: { output: decision },   // SmokeDecisionOutput（在 Step 4 已算出）
  addBlocks: [task5.id, task6.id]   // proceed 路由：释放 task-5 + task-6
})

// 并行 spawn runner + monitor（两个后台 Agent）
const cfg = <task-1 的 ConfigConfirmOutput>

// runner（task-5）
Agent({
  description: '全量 run 后台执行',
  prompt: renderRunnerPrompt(cfg, task5.id),
  schema: RUNNER_OUTPUT_SCHEMA,
  name: 'runner',
  team_name: 'rock-eval-team',
  run_in_background: true
})

// monitor（task-6 + task-7，同一个 teammate 贯穿）
// monitor 自己在 prompt 里会 CronCreate 起 3 分钟巡检
Agent({
  description: '定时巡检 + 最终报告',
  prompt: renderMonitorPrompt(cfg, task6.id, task7.id),
  schema: MONITOR_PATROL_OUTPUT_SCHEMA,  // task-6 的 schema；task-7 的 ReportOutput 由 monitor 内部切换
  name: 'monitor',
  team_name: 'rock-eval-team',
  run_in_background: true
})
```

> monitor 一个 teammate 跨 task-6 和 task-7：先跑巡检产出 `MonitorPatrolOutput`（写 task-6），
> 再跑最终报告产出 `ReportOutput`（写 task-7）。Lead 在 monitor 的 prompt 里写清楚两个阶段
> 的切换条件（task-5 completed 后切阶段二）。

### Step 6 — Phase 4 启动：诊断（task-8 / task-9 并行）

```javascript
// 等 task-7 completed，读 ReportOutput.exception_groups
const report = <task-7.metadata.output>

// 取 Top-2 异常组
const topGroups = report.exception_groups.slice(0, 2)

// 如果只有 0 或 1 个组，相应创建 0 或 1 个诊断 task（不强求凑 2 个）
const diagnoseTasks = []
for (let i = 0; i < topGroups.length; i++) {
  const g = topGroups[i]
  const taskId = i === 0 ? 'task-8' : 'task-9'
  const t = await TaskCreate({
    subject: `诊断异常组 ${g.type}`,
    description: `diagnostician 深挖 ${g.type}（count=${g.count}），产出 DiagnoseOutput`,
    activeForm: `诊断 ${g.type}`,
    addBlockedBy: [task7.id]
  })
  diagnoseTasks.push(t)

  Agent({
    description: `诊断 ${g.type}`,
    prompt: renderDiagnosticianPrompt(report.experiment_id, g, t.id),
    schema: DIAGNOSE_OUTPUT_SCHEMA,
    name: 'diagnostician',
    team_name: 'rock-eval-team',
    run_in_background: true
  })
}
```

> **exception_groups >2 的处理**：先挖 Top-2，task-10 决策后如果 Lead 觉得不够，可追加
> task-8.1 / task-9.1 挖下一批（参考 §5.2 特殊状态处理）。

### Step 7 — 调参决策（task-10）

```javascript
const task10 = await TaskCreate({
  subject: '调参决策',
  description: 'Lead 聚合 task-8/task-9 的 DiagnoseOutput，产出 TuningDecisionOutput',
  activeForm: '决策是否调参',
  addBlockedBy: ['task-8', 'task-9']   // 或实际创建的 diagnoseTasks id
})

await TaskUpdate({ taskId: task10.id, owner: 'lead', status: 'in_progress' })

// 读所有 diagnostician 的 DiagnoseOutput
const diagnoses = [<task-8.metadata.output>, <task-9.metadata.output>]

// 循环终止策略（§3.10）
const loopCount = <上一轮 task-10 的 loop_count 或 0>
const anyParamIssue = diagnoses.some(d => d.is_param_issue)

let decision
if (loopCount >= 3) {
  decision = { should_tune: false, risk_level: 'none', reason: '3 次调参未改善，停止', loop_count: loopCount }
} else if (!anyParamIssue) {
  decision = { should_tune: false, risk_level: 'none', reason: '无参数问题，停止', loop_count: loopCount }
} else {
  // 构造 tuning_params（合并 diagnoses 的 suggestion）
  const risk = classifyRisk(diagnoses)  // low / high
  decision = {
    should_tune: true,
    risk_level: risk,
    tuning_params: mergeTuningParams(diagnoses),
    reason: '...',
    loop_count: loopCount + 1
  }
}

// 高风险需先问用户
if (decision.should_tune && decision.risk_level === 'high') {
  // SendMessage 或直接问用户；拒绝则 decision.should_tune = false
}

// 注意：task-10 暂不 mark completed —— 先在 Step 8 创建 task-11（若 should_tune），
// 再回头完成 task-10 + addBlocks，避免引用未创建的 task11.id
// should_tune=false 时直接完成 task-10 不 addBlocks，循环终止
if (!decision.should_tune) {
  await TaskUpdate({
    taskId: task10.id,
    status: 'completed',
    metadata: { output: decision },
    addBlocks: []   // 循环终止，不释放任何下游
  })
  // 向用户报告最终结论，run 结束
}
// should_tune=true 时，继续 Step 8
```

### Step 8 — Operator 执行 + 循环重置（task-11 → task-5）

```javascript
// 进入 Step 8 前提：Step 7 的 decision.should_tune === true
// （should_tune=false 已在 Step 7 末尾终止）

const task11 = await TaskCreate({
  subject: '执行调参',
  description: 'operator 停止→销毁→调参→准备重跑，产出 OperatorOutput',
  activeForm: '执行调参',
  addBlockedBy: [task10.id]
})

// task-11 已创建，现在完成 task-10 解除 task-11 阻塞
await TaskUpdate({
  taskId: task10.id,
  status: 'completed',
  metadata: { output: decision },   // TuningDecisionOutput
  addBlocks: [task11.id]
})

// 派 operator
Agent({
  description: '执行调参闭环',
  prompt: renderOperatorPrompt(report.experiment_id, cfg.pass_through, decision.tuning_params, decision.risk_level, task11.id),
  schema: OPERATOR_OUTPUT_SCHEMA,
  name: 'operator',
  team_name: 'rock-eval-team',
  run_in_background: false   // operator 通常快，前台等返回
})

// 等 task-11 completed，读 OperatorOutput
const operatorOut = <task-11.metadata.output>

if (operatorOut.action_taken === 'pending_high_risk_confirmation') {
  // 转用户确认；确认后让 operator 继续执行（SendMessage 重新唤醒）
}

// === 循环重置（§3.12） ===
const newRound = decision.loop_count + 1

// 重置 task-5 / task-6 / task-7 为 pending
await TaskUpdate({
  taskId: 'task-5',
  status: 'pending',
  owner: '',
  subject: `[run-${newRound}] 启动全量 run`,
  metadata: { output: null, new_pass_through: operatorOut.new_pass_through, run_round: newRound }
})
await TaskUpdate({
  taskId: 'task-6',
  status: 'pending',
  owner: '',
  metadata: { output: null, run_round: newRound }
})
await TaskUpdate({
  taskId: 'task-7',
  status: 'pending',
  owner: '',
  metadata: { output: null }
})

// task-8/9/10/11 不重置（它们 blockedBy task-7，task-7 回 pending 后自动重新生效）

// 重新派 runner + monitor（与 Step 5 同构，prompt 用 operatorOut.new_pass_through）
// ... 回到 Step 5 的并行派发 ...
```

---

## 6. 跨会话恢复

TeamCreate 的 task 目录 `~/.claude/tasks/rock-eval-team/` 跨会话持久化。新会话中 Lead：

1. `TaskList()` 查看所有 task 状态。
2. 找 `status=in_progress` 的 task → 与用户确认是否继续。
3. 已 `completed` 的 task，读 `metadata.output` 恢复上下文（schema 对象）。
4. 仍 `pending` 且 `blockedBy=[]` 的 task → 正常派发。
5. 仍 `pending` 但有 `blockedBy` 未解除 → 等上游完成。

> **Cron 注意**：Monitor 的巡检 Cron 若用 `durable: false`（默认，见 §3.7），会话关闭即停止。
> 长跑需跨会话巡检时，创建 Cron 用 `durable: true`（写入
> `.claude/scheduled_tasks.json`）。新会话恢复时，Lead 应检查 task-6 是否 in_progress 且
> Cron 已停止，若是则重新 `CronCreate` 起巡检（用 task-6.metadata 里的 experiment_id）。

---

## 7. 与 legacy 的互操作

- **不混用**：一次回归全程 TeamCreate 或全程 legacy，不交叉。
- **共享 schema 文件**：`references/schemas.json` 只服务于 TeamCreate 模式。legacy 模式
  继续用 prompt「铁律」约束输出。
- **共享 worker prompt 内核**：smoke-oracle / smoke-nop 的判据（reward≈满分 / reward≈0）
  与 legacy 完全一致，只是输出从「自然语言结论」升级为 schema 对象。

---

## 8. 防爆规则（Lead 自查清单 — TeamCreate 专版）

- [ ] 我有没有直接跑 `regression.py` / `rc`？（应：没有）
- [ ] 我有没有读 `results/*.json` / `logs/` / `configs/`？（应：没有）
- [ ] task-1 的 ConfigConfirmOutput 是否只包含用户明确确认的字段？
- [ ] smoke teammate 的 prompt 是否写死了具体 smoke_tasks（不让 teammate 自选）？
- [ ] SmokeOutput.experiment_id 是否来自 run 命令的实际返回（非「最新文件」推断）？
- [ ] task-4 决策是否严格按 §3.5 决策表，而非 Lead 主观判断？
- [ ] Runner / Monitor 是用 `run_in_background: true` 后台 spawn（不阻塞 Lead）？
- [ ] Monitor 的巡检是否用 CronCreate（每 3 分钟，session-only），run 结束已 CronDelete？
- [ ] Monitor 巡检判据是否只用简化 2 条（dispatched 不降 + error 堆积），没塞 pass rate / 单 task 超时？
- [ ] Diagnostician 回的是 DiagnoseOutput 对象（根因/异常类型/task列表/是否参数问题/建议），不是原文？
- [ ] 并行 Diagnostician 数量 ≤ 2？
- [ ] task-10 的循环终止策略是否严格执行（loop_count ≥3 或无 param issue 即停）？
- [ ] 高风险调参（image/cluster/model/agent/namespace）是否经用户确认？
- [ ] task-11 完成后是否按 §3.12 显式重置 task-5/6/7 状态触发循环（不靠 blocks 自动触发）？
- [ ] 每个 worker prompt 写死了 experiment id？
- [ ] 跨会话恢复时先 `TaskList` 检查残留，未与用户确认前不擅自重开？
- [ ] 巡检 Cron 在跨会话恢复时是否重新 `CronCreate`（session-only 已失效）？
