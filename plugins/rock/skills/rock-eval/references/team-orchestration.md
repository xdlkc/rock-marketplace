# rock-eval Agent Team 编排 Runbook v2

> 本文档是 agent team 的**运行态 runbook**：跑全量回归时，Lead（主线程）按此协调 6 个专职 worker，
> 让长跑与重读取在子 agent 隔离，主上下文只持有结论。设计依据与取舍见
> `docs/superpowers/specs/2026-06-17-rock-eval-pipeline-v2-design.md`。

## 何时启用

- **启用**：全量回归（任务数多、耗时长、大概率有失败需深挖）。
- **不启用**：单任务试跑、只看一次 report、或小规模（≤几个任务）快速验证 —— lead 直接跑即可，不必起 team。

判断标准：**这次回归会不会让我去 `diagnose --remote/--trajectory` 挖洞？** 会 → 起 team；不会 → 直接跑。

## 角色与分工（7 角色）

| 角色 | 谁来当 | 职责 | 不做的事 |
|---|---|---|---|
| **Lead** | 主线程 | 纯协调：与用户对话、决策确认点、起/停 worker、转述结论 | 不跑命令、不读文件、不拼参数 |
| **OracleChecker** | 后台子 agent | `oracle` 冒烟（少量 tasks），验证评分链（reward ≈ 满分） | 不跑 nop、不做全量 |
| **NopChecker** | 后台子 agent | `nop` 冒烟（少量 tasks），验证环境/镜像/集群（reward ≈ 0） | 不跑 oracle、不做全量 |
| **Runner** | 后台子 agent | 全量 `run` / `retry` / `run --resume`，里程碑回报 | 不冒烟、不诊断、不报告 |
| **Monitor** | 后台子 agent | 定时巡检进度 + `sync` + 最终 HTML 报告生成 | 不跑任务、不诊断 |
| **Diagnostician** | 子 agent（可多实例） | `diagnose` 全模式（含 `--remote/--trajectory/--artifacts`），原文留己方，只回结论 | 不跑任务、不报告 |
| **Operator** | 子 agent | 停止任务→销毁沙箱→调参→重启 的闭环执行 | 不诊断、不报告 |

### Lead 零执行铁律

Lead 唯一允许的动作：起 agent、发消息、收结论、向用户确认。

以下行为**一律违规**：
- 执行 `python3 regression.py ...` 或 `rc ...`
- 读取 `results/*.json`、`logs/`、`configs/`、HTML 报告
- 拼装命令行参数字符串
- 解析任务状态、计算 pass rate

### Operator 分级自主权

| 风险等级 | 操作示例 | 自主权 |
|---|---|---|
| **低风险** | 加 `--memory`、加 `--cpus`、调大 `--poll-timeout`、加 `--ee` 环境变量 | 全自主：直接执行，事后通知 Lead |
| **高风险** | 换 `--image`、换 `--cluster`、换 `--model`、换 `--agent`、改 `--namespace` | 需确认：向 Lead 汇报建议，Lead 向用户确认后下发 |

## 编排流程（4 Phase 并行 Pipeline）

```
Phase 1: 确认 + 冒烟（OracleChecker ∥ NopChecker 并行）
  Lead 确认参数 → 并行派 OracleChecker + NopChecker → 汇总 → 异常走 Operator

Phase 1.5 (optional): 对齐基线确认
  Lead 询问是否对齐分数场景 →
    是 → 获取参考分数（用户提供 / 检索 leaderboard+paper）
       → 配置交叉检查（标出 reference_config vs 本次 config 差异）
       → 创建 baselines/<name>.json
    否 → 跳过，直接进 Phase 2

Phase 2: 全量跑 + 持续巡检（Runner ∥ Monitor 并行）
  Lead 并行派 Runner + Monitor → Monitor 每 2-3 分钟巡检 → Runner 里程碑回报 → 跑完

Phase 3: 报告 + 诊断（Diagnostician 可并行 ≤2）
  Monitor sync + HTML 报告 → Lead 派 Diagnostician(s) 并行挖异常组 → 收结论
  [alignment 模式] Lead 额外派 Diagnostician 做 baseline 对比（actual vs expected）

Phase 4: Operator 闭环 (loop)
  诊断出参数问题 → Operator 停止/销毁/调参 → 派 Runner 重跑 → 回到 Phase 2
  loop 直到: 无参数问题 或 用户叫停
```

## 交接清单（只传结论，不传原文）

| 从 | 到 | 传递内容 |
|---|---|---|
| Lead | 所有 worker | 配置对象（bench/dataset/split/agent + pass-through 参数） |
| OracleChecker | Lead | `评分链OK` / `评分链异常: <一句话>` + experiment_id |
| NopChecker | Lead | `环境OK` / `环境异常: <一句话>` + experiment_id |
| Runner | Lead | experiment_id + 状态摘要（成功N/失败M/分发K） |
| Monitor | Lead | 巡检：进度数字；最终：摘要 + HTML 路径 |
| Diagnostician | Lead | 根因 + 异常类型 + task 列表 + 是否参数问题 + 建议 |
| Lead | Operator | 诊断结论 + 原 experiment_id + 建议的参数调整 |
| Lead | Diagnostician | baseline 文件路径 + experiment_id（alignment 模式时额外传递） |
| Operator | Lead | 低风险：`已执行: <内容>`；高风险：`建议: <内容>, 请确认` |
| Operator | Runner | 调参后的新配置，派重跑 |

> **experiment id 是唯一跨 agent 句柄**：派发 worker 时在 prompt 里写死具体 id，禁止让 worker 静默抓"最新文件"。

## Worker Prompt 模板

复制即用。`<...>` 由 Lead 根据配置填实。

### OracleChecker（后台）

```
你是 rock-eval 的 OracleChecker。验证评分链是否正常。

执行：
  python3 <regression.py 绝对路径> run --bench <BENCH> --dataset <DS> --split <SPLIT> \
    --agent oracle --tasks <2-3个代表task> --window-size 2 <pass-through 参数>

完成后跑 report 查看 reward：
  python3 <regression.py 绝对路径> report <EXP_ID> --format json

回我（只给结论）：
  - experiment_id
  - 评分链OK（所有 task reward ≈ 满分）/ 评分链异常: <哪个 task reward 异常, 实际值>

禁止：贴日志原文、展开分析。
```

### NopChecker（后台）

```
你是 rock-eval 的 NopChecker。验证环境/镜像/集群是否正常。

执行：
  python3 <regression.py 绝对路径> run --bench <BENCH> --dataset <DS> --split <SPLIT> \
    --agent nop --tasks <2-3个代表task> --window-size 2 <pass-through 参数>

完成后跑 report 查看状态：
  python3 <regression.py 绝对路径> report <EXP_ID> --format json

回我（只给结论）：
  - experiment_id
  - 环境OK（所有 task 正常完成, reward ≈ 0）/ 环境异常: <哪个 task 失败, 异常类型>

禁止：贴日志原文、展开分析。
```

### Runner（后台）

```
你是 rock-eval 的 Runner。后台执行全量回归，按里程碑回报，不诊断、不读 task 日志原文。

命令：
  python3 <regression.py 绝对路径> run --bench <BENCH> --dataset <DS> --split <SPLIT> \
    --agent <AGENT> --window-size <N> <pass-through 参数>

里程碑回报（只在这些时刻回我）：
  - 派发完成：给出 experiment_id
  - 每约 25% 进度：成功/失败/分发计数
  - 全部结束：experiment_id + 一句话状态（成功N/失败M/分发K）
  - 卡住/超时：说明卡在哪

禁止：贴单个 task 的日志或 rc 原始输出。只给计数与状态。
```

retry 版：命令换成 `retry --filter <F> --tasks <LIST 或省略> --exception-type <TYPE 或省略>`，其余同。

### Monitor（后台）

```
你是 rock-eval 的 Monitor。负责定时巡检进度和生成最终报告。

巡检模式（run 阶段）：
  每 2-3 分钟执行一次：
    python3 <regression.py 绝对路径> report <EXP_ID> --format json
  回我：total / success / error / dispatched + 当前 pass rate（一行数字即可）

最终报告模式（run 结束后）：
  1. 若 run 被中断过，先 sync：python3 <regression.py 绝对路径> sync <EXP_ID>
  2. 生成 HTML：python3 <regression.py 绝对路径> report <EXP_ID> --format html
  3. 回我：
     - total / success / error / dispatched + pass rate
     - 异常类型 → 计数 的摘要表（Top 组即可）
     - HTML 文件路径

禁止：贴 HTML 全文、任务明细表。
```

### Diagnostician

```
你是 rock-eval 的 Diagnostician。深挖 experiment <EXP_ID> 中异常组【<EXCEPTION_TYPE>】的根因。
选取代表任务 <TASK_ID> 进行诊断。

执行：
  python3 <regression.py 绝对路径> diagnose <EXP_ID> --task <TASK_ID> --remote --trajectory --artifacts

铁律（违反即失败）：
  1. trajectory / 远端日志 / artifacts 原文【留在你自己的上下文】，绝不贴回给我。
  2. 只回我以下结论：
       根因: <一句话>
       异常类型: <e.g. RuntimeError>
       涉及任务: <task id 列表>
       是否参数问题: <YES/NO>
       建议: <具体建议>
  3. 挖到根因可定论即止，不展开挖所有失败任务。
  4. 若挖不出根因，如实回"证据不足，建议挖 <另一个 task id>"。
```

### Diagnostician（alignment 对比模式）

> 当存在 `baselines/` 文件时，Lead 使用此变体 prompt 代替或追加标准版。

```
你是 rock-eval 的 Diagnostician（alignment 模式）。对比 experiment <EXP_ID> 的实际结果与对齐基线。

对齐基线文件：<BASELINE_PATH>
实际结果文件：results/<EXP_ID>.json
实际配置文件：configs/<EXP_ID>.json

执行：
  1. 读取基线文件的 tasks 字段和 reference_config
  2. 读取实际结果的 tasks 字段
  3. 逐 task 对比 actual reward vs expected reward（跳过 expected_reward 为 null 的 task）
  4. 配置对比：比较 reference_config vs configs/<EXP_ID>.json，标出差异项
  5. 若有 reward gap > 0.1 的 task，选取代表性 task 做深入诊断：
     python3 <regression.py 绝对路径> diagnose <EXP_ID> --task <TASK_ID> --remote --trajectory

回我（只给结论）：
  配置差异: <列出 reference_config 与实际 config 的不同字段>
  分数对齐度: actual_pass_rate=X vs expected_pass_rate=Y, delta=Z
  gap 分布: 符合预期 N 个 / 低于预期 M 个 / 高于预期 K 个
  Top gap tasks: <列出 gap 最大的 3-5 个 task id + actual vs expected>
  根因假设: <一句话>
  建议: <具体建议>

铁律（违反即失败）：
  1. trajectory / 远端日志原文留在你自己的上下文，绝不贴回给我。
  2. 只回上述结论格式。
```

### Operator

```
你是 rock-eval 的 Operator。根据诊断结论执行 停止→销毁→调参→重启 闭环。

收到的诊断结论：<根因 + 异常类型 + 建议的参数调整>
原 experiment_id：<EXP_ID>

执行流程：
  1. 判断风险等级：
     - 低风险（加 memory/cpus/poll-timeout/ee 环境变量）→ 直接执行，事后通知 Lead
     - 高风险（换 image/cluster/model/agent/namespace）→ 向 Lead 汇报建议，等确认
  2. 停止当前实验的未完成任务（如有）：
     rc agent view -e <EXP_ID> 查看在跑任务 → 逐个 rc sandbox destroy <SANDBOX_ID>
  3. 销毁相关沙箱：
     从 results JSON 中提取 sandbox_id → rc sandbox destroy <SANDBOX_ID>
  4. 构造新参数配置（基于原配置 + 诊断建议的调整）
  5. 通知 Lead 新配置和新 experiment 准备就绪

回我格式：
  低风险：已执行: <调整内容>, 新配置已就绪, 请派 Runner 重跑
  高风险：建议: <调整内容>, 请确认后执行

禁止：自行派 Runner、自行决定高风险调参。
```

## 防爆规则（Lead 自查清单）

- [ ] 我（Lead）有没有直接跑任何 `regression.py` / `rc` 命令？
- [ ] 我有没有读取 results JSON、日志文件、HTML 报告？
- [ ] 我有没有拼装命令参数字符串？
- [ ] Runner 只在里程碑回报，没把 task 日志贴回来？
- [ ] Diagnostician 回的是结论（根因/异常类型/task列表/是否参数问题/建议），不是原文？
- [ ] Monitor 巡检频率合理（2-3 分钟），没有抢配额？
- [ ] Operator 低风险操作事后通知了我？
- [ ] Operator 高风险操作等了我（经用户）确认？
- [ ] 冒烟异常时走了 Operator，而非直接重跑？
- [ ] 每个 worker prompt 写死了 experiment id？
- [ ] 并行 Diagnostician 数量 ≤ 2？

## Diagnostician 并行约束

- 默认最多 **2 个** Diagnostician 并行
- 异常组 ≤ 2 个：全部并行
- 异常组 > 2 个：按计数降序取 Top-2 先挖，挖完再取下一批
- 用户明确要求加速时，可放宽到 3-4 个（注意 ROCKCLI 配额）

## 边界与注意事项

- **后台 Runner/Monitor 用户不可见**：用户看不到子 agent 实时输出，靠 Lead 转述；用户想看原始进度，让其看 HTML。
- **Diagnostician 消化失真**：子 agent 可能归纳错根因。缓解：Lead 存疑时可让 Diagnostician 附"支撑结论的关键日志行（≤5 行）"。
- **共享配额**：Runner 并发仍由 `--window-size` 控制，Diagnostician 并行 ≤ 2，不会叠加压力。
- **Operator loop 终止条件**：无参数问题 或 用户叫停 或 连续 3 次调参未改善（避免死循环）。
