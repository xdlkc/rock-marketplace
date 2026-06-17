> **⚠️ ARCHIVED** — 本文档为 v1 设计，已被 `2026-06-17-rock-eval-pipeline-v2-design.md` 替代。
> 保留作为历史参考，运行态请参考 v2。

# rock-eval Agent Team 编排设计

> 日期：2026-06-17
> 目标：为 rock-eval 全量回归设计一套 agent team 编排方案，解决"回归跑得久、中途排查多、主上下文容易爆"的问题。

## 1. 背景与现状

`regression.py` 是 `rockcli`（`rc`）的回归编排壳，五个子命令 `run / report / sync / diagnose / retry`
通过 `results/<experiment_id>.json` + experiment id 串联，状态全部落盘。耗时与上下文压力分布如下：

| 子命令 / 操作 | 耗时 | 对主上下文的压力 |
|---|---|---|
| `run` / `retry`（滑动窗口全量跑） | **很长**（每任务 poll 默认 600s，并发 ~10） | 低（进度可轮询，不必把日志读进来） |
| `report`（text/json/html） | 快 | 低（聚合摘要） |
| `sync` | 中（网络，并发 10） | 低 |
| `diagnose`（overview / `--task` 纯本地） | 快 | 中（去重错误消息 Top-10） |
| `diagnose --remote`（拉服务器日志，遍历 5 个候选名逐个 `rc agent fs cat`） | 中 | **高** |
| `diagnose --trajectory`（拉完整 agent 执行轨迹，单次截断 3000 字符） | 中 | **极高 —— 主要上下文杀手** |
| `diagnose --artifacts` | 中 | 高 |

核心矛盾：**深挖失败任务**（`diagnose --task --remote --trajectory`）是定位问题的必经之路，
却恰好是把大量原始数据灌进上下文的操作。一次全量回归往往有多个失败组、每组要挖代表任务，
原始日志/轨迹若全部进主上下文，几轮就爆。

## 2. 设计原则

1. **状态落盘、上下文不搬数据**。所有子命令本就靠 `results/`/`logs/`/`configs/` 文件传递，
   team 编排只交换**结论与 experiment id**，不交换原始日志。
2. **脏活外包**。长跑（run/retry）与重读取（diagnose deep-dive）放后台子 agent，
   主线程只接「进度 / 结论 / 需要人决策的选项」。
3. **人在环上**。pass-through 参数（image/cluster/model/cpus/memory…）、是否先 oracle/nop 冒烟、
   并发值、retry 哪些异常组 —— 这些是文档明确的**确认点**，由 lead 在主线程向用户确认，
   不下放给子 agent 自主决定。
4. **职责单一**。每个子 agent 只做一件事，产物干净可审查。

## 3. 角色设计

一个 lead + 三个专职 worker。**不做并行挖洞的 fan-out**（见 §6 不做的事）。

### Lead（主线程，不另起 agent）

- **唯一**与用户对话的角色，负责所有「需人决策」的确认点。
- 唯一持有 experiment id 的全局视图，协调 worker 顺序与交接。
- 自己**不读** trajectory / 远端日志原文 —— 永远从 worker 收结论。
- 决策"挖到什么程度算够"（避免无限深挖）。

### Runner（后台子 agent）—— 长跑专家

- 执行 `run` / `retry` / `run --resume`，在**后台**跑（`run_in_background`），长时不阻塞主线程。
- 监控进度，只在**里程碑**向 lead 回报：派发完成、N% 成功、整体结束、或卡住超时。
- 不做诊断。跑完交付：`experiment_id` + 一句话状态摘要（成功/失败/分发计数）。
- 中途若被中断，lead 指示它先 `sync` 再 `report`，而非把日志拉回来。

### Diagnostician（前台/后台子 agent）—— 挖洞专家

- 执行 `diagnose` 全部模式，**包括** `--remote` / `--trajectory` / `--artifacts`。
- **关键**：trajectory / 远端日志的原文**留在它自己的上下文里**，它负责消化后只回传：
  - 根因一句话（e.g. "Docker 镜像拉取超时" / "评分文件缺失 RewardFileNotFoundError"）。
  - 归类到的异常类型（用于 retry 过滤）。
  - 涉及的 task id 列表（用于 `--tasks` 精确重跑）。
  - 建议的下一步（fix 环境 / retry 某异常组 / 改参数重跑）。
- 即"脏活的隔离舱"：把 3000 字符的轨迹 + 多个候选日志压缩成几行结论。
- 一次只挖**一个异常组的代表任务**；挖完结论给 lead，由 lead 决定是否挖下一个组。

### Reporter（轻量子 agent，可选）

- 执行 `report`（生成 HTML dashboard）与 `sync`。
- 这两个操作轻、但仍是"读结果再转述"的活，外包可让主上下文更干净。
- 交付：状态摘要（total/success/error/dispatched + pass rate）+ HTML 路径。
- 简单场景 lead 可直接自己做，**非强制**角色。

## 4. 编排流程（带交接的状态机）

```
                        ┌─────────────────────────────────────┐
                        │  Lead: 与用户确认参数 + 是否冒烟      │
                        │  (bench/dataset/agent/image/cluster/ │
                        │   model/cpus/memory/concurrency…)    │
                        └─────────────────┬───────────────────┘
                                          │ 用户确认
                        ┌─────────────────▼───────────────────┐
                        │  [可选] Runner: oracle/nop 冒烟(后台)  │
                        │  → 结论: 环境OK / 环境有问题           │
                        └─────────────────┬───────────────────┘
                                          │ 环境OK
                        ┌─────────────────▼───────────────────┐
                        │  Runner: run 全量(后台, 里程碑回报)    │
                        │  → 交付 experiment_id + 状态摘要       │
                        └─────────────────┬───────────────────┘
                                          │ 跑完
                        ┌─────────────────▼───────────────────┐
                        │  Reporter: report + (中断则先 sync)   │
                        │  → 交付 pass rate + error 分组摘要     │
                        └─────────────────┬───────────────────┘
                                          │ 有 error
                        ┌─────────────────▼───────────────────┐
                        │  Diagnostician: 按异常组逐个挖代表任务 │
                        │  (--remote --trajectory, 原文留己方)   │
                        │  → 交付 根因 + 异常类型 + task列表 + 建议 │
                        └─────────────────┬───────────────────┘
                                          │ Lead 判断可修 / 需重跑
                        ┌─────────────────▼───────────────────┐
                        │  Lead: 向用户确认 retry 范围           │
                        │  (哪些异常组 / --tasks 列表 / 改参数?) │
                        └─────────────────┬───────────────────┘
                                          │
                        ┌─────────────────▼───────────────────┐
                        │  Runner: retry(后台) → 回到 report 环节 │
                        └─────────────────────────────────────┘
```

**关键交接点（全部只传结论，不传原文）**：

| 从 | 到 | 传递内容 |
|---|---|---|
| Runner | Lead | `experiment_id` + 一句话状态（成功N/失败M/分发K） |
| Reporter | Lead | pass rate + 异常类型→计数 的摘要表 |
| Lead | Diagnostician | experiment_id + 要挖的异常组/代表 task id |
| Diagnostician | Lead | 根因 + 异常类型 + task 列表 + 建议 |
| Lead | Runner | retry 命令（experiment_id + `--filter`/`--tasks`/`--exception-type`） |

## 5. 防爆的具体规则（写进 worker 的 prompt）

1. **Runner 只报里程碑**：派发完成、每 25% 进度、结束、卡住。**禁止**把每个 task 的日志贴回来。
2. **Diagnostician 三条铁律**：
   - trajectory / 远端日志原文**留在自己上下文**，回 lead 时只给结论。
   - 一次只挖**一个代表任务**，挖完交结论，等 lead 决定下一个。
   - 挖到根因可定论即止，**不展开挖所有失败任务**（同根因只挖一个代表）。
3. **Lead 永不直接 `diagnose --remote/--trajectory`**：要原文就让 Diagnostician 去挖并转述。
4. **report 优先 HTML**：Reporter 生成 HTML 让用户/lead 看文件，不把全表灌进上下文；lead 只取摘要数字。
5. **experiment id 是唯一跨 agent 句柄**：所有 worker prompt 里写死"用这个 id"，避免静默抓到最新文件造成错配。

## 6. 不做的事

1. **不做并行 fan-out 挖洞**。虽然可以一次性派多个 Diagnostician 并行挖不同异常组，
   但：(a) 同时拉多份 trajectory 对共享 ROCKCLI 配额是雪上加霜；(b) 并行结论再汇总反而
   把多组原始上下文风险叠加到 lead。**串行挖、挖一个交一个**更可控。除非失败组数量很多且
   用户明确要求加速，才考虑有限并行（≤2）。
2. **不让子 agent 决定 pass-through 参数**。image/cluster/model/cpus/memory 等一律 lead 在主线程
   向用户确认后下发，子 agent 只透传，不猜默认。
3. **不做自动化"修完再跑"循环**。是否 retry、改不改参数、换不换 image，都是 lead 问用户的人决策点，
   不由 team 自主多轮重跑（避免烧配额、避免无人监督地改动环境）。
4. **不引入新 IPC 机制**。不写新的状态文件、不上消息队列，完全复用 `regression.py` 既有的
   results/logs/configs 落盘 + experiment id 解析。设计是**编排约定**，不是代码改造。

## 7. 落点与文档

- 本设计文档：`docs/superpowers/specs/2026-06-17-rock-eval-agent-team-design.md`（即本文件）。
- 运行态引用：`plugins/rock/skills/rock-eval/references/team-orchestration.md` ——
  供 skill 运行时 agent 读取的精简 runbook（角色 prompt 模板 + 交接清单），SKILL.md 加一行指向它。
- 两者关系：本设计文档讲**为什么这么设计**（约束、取舍、不做的事）；
  team-orchestration.md 讲**运行时怎么照着做**（可直接复制的 worker prompt、交接表）。

## 8. 验证计划

设计为编排约定、无代码改动，验证方式：

1. **走查一次真实回归**：挑一个小 bench，按本流程跑 run → report → diagnose → retry，
   确认 lead 主上下文始终只持有结论（experiment id + 摘要 + 根因），不持有 trajectory 原文。
2. **断点检查**：在 diagnose 环节后，目测 lead 上下文规模 —— 应远小于"直接在主线程跑 diagnose --trajectory"。
3. **交接正确性**：确认每个 worker 拿到的 experiment id 与 lead 一致，无静默抓错文件。
4. **人决策未被绕过**：确认 pass-through 参数、冒烟与否、retry 范围均在主线程经用户确认。

## 9. 风险与边界

- **后台 Runner 不可见**：用户看不到子 agent 实时输出，需靠里程碑回报 + lead 转述进度。
  若用户想看原始进度，lead 可让其自行 `report` 或看 HTML，而非把日志拉回主上下文。
- **Diagnostician 消化失真**：子 agent 可能把根因归纳错。缓解：lead 收到结论后若存疑，
  可让 Diagnostician 附上"支撑结论的关键日志行（≤5 行）"而非全文。
- **共享配额**：并发受 ROCKCLI 配额约束（脚本无硬上限，建议 ~10）。team 不额外加压 ——
  Runner 的并发仍由 `--window-size` 控制，Diagnostician 串行挖洞，不会与 Runner 抢配额。
