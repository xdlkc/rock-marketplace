# rock-eval Agent Team 编排 Runbook

> 本文档是 `team-orchestration` 的**运行态 runbook**：跑全量回归时，lead（主线程）按此协调一组专职 worker，
> 让长跑与重读取在子 agent 隔离，主上下文只持有结论。设计依据与取舍见
> `docs/superpowers/specs/2026-06-17-rock-eval-agent-team-design.md`。

## 何时启用

- **启用**：全量回归（任务数多、耗时长、大概率有失败需深挖）。
- **不启用**：单任务试跑、只看一次 report、或小规模（≤几个任务）快速验证 —— lead 直接跑即可，不必起 team。

判断标准：**这次回归会不会让我去 `diagnose --remote/--trajectory` 挖洞？** 会 → 起 team；不会 → 直接跑。

## 角色与分工

| 角色 | 谁来当 | 职责 | 上下文压力 |
|---|---|---|---|
| **Lead** | 主线程 | 与用户对话、所有需人决策的确认点、协调 worker、唯一全局 experiment-id 视图、**永不直接挖洞** | 低 |
| **Runner** | 后台子 agent | `run`/`retry`/`run --resume` 长跑 + 里程碑进度回报 | 低（只传结论） |
| **Reporter** | 子 agent | `report`（生成 HTML）+ `sync`，转述状态摘要 | 低 |
| **Diagnostician** | 子 agent | `diagnose` 全模式含 `--remote/--trajectory/--artifacts`，**原文留己方**，只回结论 | 子 agent 内高，lead 低 |

**铁律**：状态全落盘（`results/`/`logs/`/`configs/`），worker 之间只交换**结论与 experiment id**，不交换原始日志/轨迹。

## 编排流程

```
1. Lead 与用户确认参数 + 是否 oracle/nop 冒烟
2. [可选] Runner 后台跑 oracle/nop 冒烟 → 回"环境OK/有问题"
3. Runner 后台跑全量 run → 回 experiment_id + 状态摘要
4. Reporter 跑 report（中断则先 sync）→ 回 pass rate + 异常分组摘要
5. Diagnostician 逐异常组挖代表任务（原文留己方）→ 回根因+异常类型+task列表+建议
6. Lead 向用户确认 retry 范围（哪些异常组/--tasks/改参数）
7. Runner 后台 retry → 回到步骤 4
```

## 交接清单（只传结论，不传原文）

| 从 | 到 | 传递内容 |
|---|---|---|
| Runner | Lead | `experiment_id` + 一句话状态（成功N/失败M/分发K） |
| Reporter | Lead | pass rate + 异常类型→计数 摘要表 + HTML 路径 |
| Lead | Diagnostician | `experiment_id` + 要挖的异常组 / 代表 task id |
| Diagnostician | Lead | 根因 + 异常类型 + task 列表 + 建议 |
| Lead | Runner | retry 命令（`experiment_id` + `--filter`/`--tasks`/`--exception-type` + 透传参数） |

> **experiment id 是唯一跨 agent 句柄**：派发 worker 时在 prompt 里写死具体 id，禁止让 worker 静默抓"最新文件"，避免错配。

## Worker Prompt 模板

复制即用。`<EXP_ID>`、`<...>` 由 lead 填实。

### Runner（后台）

```
你是 rock-eval 回归的 Runner。后台执行下述命令，按里程碑回报，不诊断、不读 task 日志原文。

命令：
  python3 <regression.py 绝对路径> run --bench <BENCH> --dataset <DS> --split <SPLIT> \
    --agent <AGENT> --window-size <N> <用户指定的透传参数，原样带上>

里程碑回报（只在这些时刻回我，不要每条日志都贴）：
  - 派发完成：给出 experiment_id
  - 每约 25% 进度：成功/失败/分发计数
  - 全部结束：experiment_id + 一句话状态（成功N/失败M/分发K）
  - 卡住/超时：说明卡在哪，建议 sync

禁止：把单个 task 的日志、rc 原始输出贴回来。只给计数与状态。
```

retry 版：命令换成 `retry --filter <F> --tasks <LIST 或省略> --exception-type <TYPE 或省略>`，其余同。

### Reporter

```
你是 rock-eval 的 Reporter。对 experiment <EXP_ID> 执行：

1. 若 run 可能被中断过，先 sync：<regression.py> sync <EXP_ID>
2. 生成 HTML 报告：<regression.py> report <EXP_ID> --format html
3. 回我（只给摘要，不要把任务全表贴回来）：
   - total / success / error / dispatched + pass rate
   - 异常类型 → 计数 的摘要表（Top 组即可）
   - HTML 文件路径

禁止：把 HTML 全文、任务明细表灌给我。我只要数字与路径。
```

### Diagnostician

```
你是 rock-eval 的 Diagnostician。深挖 experiment <EXP_ID> 中【指定异常组/代表任务 <TASK_ID>】的根因。

执行：
  python3 <regression.py 绝对路径> diagnose <EXP_ID> --task <TASK_ID> --remote --trajectory --artifacts

铁律（违反即失败）：
  1. trajectory / 远端日志 / artifacts 的原文【留在你自己的上下文】，绝不贴回给我。
  2. 只回我以下结论，格式严格如下：
       根因: <一句话，e.g. "Docker 镜像拉取超时 ImagePullTimeout">
       异常类型: <e.g. RuntimeError>
       涉及任务: <task id 列表>
       建议: <换 image / 加 --ee xxx / retry 该异常组 / 改参数重跑>
  3. 挖到根因可定论即止，不要展开挖所有失败任务。一个代表任务足矣。
  4. 若挖不出根因，如实回"证据不足，建议挖 <另一个 task id>"，不要编造。
```

## 防爆规则（lead 自查清单）

- [ ] 我（lead）有没有直接跑 `diagnose --remote/--trajectory`？有 → 立即改派 Diagnostician。
- [ ] Runner 是不是只在里程碑回报，没把 task 日志贴回来？
- [ ] Diagnostician 回的是结论四要素（根因/异常类型/task列表/建议），而非原文？
- [ ] pass-through 参数（image/cluster/model/cpus/memory…）是我向用户确认后下发的，没让子 agent 猜默认？
- [ ] 是否先 oracle/nop 冒烟 —— 我问过用户了？
- [ ] retry 范围是我向用户确认的，没自主多轮重跑？
- [ ] 每个 worker prompt 里写死了 experiment id，没让它静默抓最新文件？

## 边界与注意事项

- **串行挖洞**：Diagnostician 一次挖一个异常组的代表任务，挖完交结论、等 lead 决定下一个。
  不并行 fan-out（并行拉多份 trajectory 对共享 ROCKCLI 配额是雪上加霜）。
- **后台 Runner 用户不可见**：用户看不到子 agent 实时输出，靠 lead 转述里程碑；用户想看原始进度，
  让其自行 `report` 或看 HTML，不要把日志拉回主上下文。
- **并发受 ROCKCLI 配额约束**（脚本无硬上限，建议 `--window-size ~10`）；team 不额外加压，
  Diagnostician 串行、不与 Runner 抢配额。
- **不做的事**：不让子 agent 决定 pass-through 参数；不做自动化"修完再跑"循环（retry 与否、改不改参数都是人决策点）；
  不引入新 IPC，完全复用 `regression.py` 既有的 results/logs/configs 落盘 + experiment id 解析。
