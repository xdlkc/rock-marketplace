# rock-eval: 巡检 agent 接入 Cron + rock-agent-debug 确认实际任务进展

> 日期 2026-06-17。基于 1.4.1（HEAD e3f6ef5）。
> 根因：巡检角色 Monitor 只跑 `report --format json` 读本地数字，不主动查 job
> 远端实际进展、无任何"卡住/失败"判据 → job 已出问题（agent 崩溃/全失败/卡死）
> 时本地仍是 dispatched，Monitor 误判为"还在执行"。

## 用户决策（已拍板）
1. Cron 用途：**定时周期巡检**（独立于 run 进程）。
2. Cron 周期：**每 3 分钟**（沿用 Monitor 现有节奏）。
3. 巡检内容：`sync` 拉远端真实进展 + 卡住判据。
4. rock-agent-debug：**可疑才深挖**，不全量跑。
5. 可疑判据（4 条，全选）：
   ① dispatched 长期不降（连续 N 次巡检不下降）
   ② error 堆积（error 数超阈值或持续增长）
   ③ pass rate 异常低（远低于预期/参考基线）
   ④ 单 task 超时（停留 dispatched 超过推理超时 timeout 的 1.5 倍）

## 关键实现约束（影响改法）
- **不改 regression.py**。report/sync/diagnose 子命令保持原样。
- 判据①"连续 N 次不降"需要**跨巡检次的历史**。report 是无状态汇总，没有历史。
  → 由巡检 agent 维护一个本地巡检状态文件（如 `logs/<EXP_ID>/monitor-state.json`），
    每次巡检读上次快照、写本次快照，在 prompt 层面用该文件算"不降次数"。
  → 这属于 Monitor 的巡检产物，与 results/logs/configs 同级目录体系一致。
- Cron 工具：用 CronCreate（session 内定时）。Monitor 角色描述里写明"用 Cron 工具
  每 3 分钟拉起一次巡检"，而非靠 run 进程内手轮询。
- rock-agent-debug 是单 job 深挖、不批量、按需触发。巡检 agent 外层编排：
  发现可疑 job → 对该 job（experiment_id + job_name）触发 rock-agent-debug 深挖。

## 改动范围（最小，2 个文件）

### A. references/team-orchestration.md（核心改动）
位置：Monitor 角色描述（:22）+ Phase 2（:56-57）+ Monitor Prompt 模板（:147-166）。

1. **Monitor 职责描述（:22）**：在"定时巡检进度 + sync + 最终 HTML 报告"基础上，
   明确：巡检用 **Cron 工具每 3 分钟拉起**；巡检先 `sync` 拉远端真实进展再 `report`；
   发现可疑信号时对可疑 job 调用 **rock-agent-debug** 深挖确认实际进展。

2. **Phase 2（:56-57）**：把"Monitor 每 2-3 分钟巡检"改为"Monitor 用 Cron 每 3 分钟
   定时巡检（独立于 Runner 进程，即使 run 被 background 化/终端关掉仍定时跑）"。

3. **Monitor Prompt 巡检模式（:152-155）**：重写为带 sync + 判据 + 深挖的完整流程：
   ```
   巡检模式（run 阶段，Cron 每 3 分钟触发一次）：
     1. 先 sync 拉远端真实进展：python3 <regression.py 绝对路径> sync <EXP_ID>
     2. 再汇总：python3 <regression.py 绝对路径> report <EXP_ID> --format json
        记录本次 total/success/error/dispatched + pass rate
     3. 读写巡检状态：logs/<EXP_ID>/monitor-state.json
        读上次快照，算"dispatched 连续不降次数"、"error 是否持续增长"
        写本次快照（含每 task 首次进入 dispatched 的时间戳，用于判单 task 超时）
     4. 判可疑（满足任一即视为 job 出问题，不再当"正常执行"）：
        ① dispatched 数量连续 ≥3 次巡检不下降
        ② error 数 > 总任务 10% 或连续增长
        ③ pass rate 远低于预期/参考基线（对齐场景：低于 expected_pass_rate 的 0.7 倍）
        ④ 某 task 停留 dispatched 超过推理超时 timeout 的 1.5 倍
     5. 若判定可疑 → 对该 job 调用 rock-agent-debug 深挖：
        提供 experiment_id + job_name，让其拉 trial 级真实状态（result.json 异常字段、
        trajectory、exception.txt、docker container 状态），确认"假执行"根因
     6. 回我（一行）：状态=正常/可疑 + 当前数字 + （可疑时）根因一句话
   ```
   注：判据①的"3 次"是默认阈值；判据③对齐场景才适用；判据④需 monitor-state 记
   task 首 dispatched 时间。

4. **Monitor 最终报告模式（:157-159）**：保留"若中断过先 sync"，补充"巡检 Cron
   在 run 结束后应被 CronDelete 清理，避免空跑"。

### B. SKILL.md（入口/说明同步）
位置：Sync 段（:230-241）+ Quick Start + decision tree（巡检/监控相关）。

1. 在 Sync 段或邻近补一句：巡检（Monitor）用 Cron 每 3 分钟定时 sync+report+判可疑，
   可疑时调 rock-agent-debug 确认实际进展；run 结束后清理该 Cron。
2. Bundled Resources（:316）角色清单里 Monitor 描述同步（若该处列了职责）。
3. decision tree 若有"巡检/监控"分支，补 Cron + rock-agent-debug 引用。

### C. 不改
- regression.py（sync/report/diagnose 原样）。
- rock-agent-debug skill（它本身按需被调用，不改）。
- 数据格式（monitor-state.json 是巡检运行时产物，不入 data-formats schema，
  但可在 team-orchestration.md 里描述其结构：{last_dispatched_count, no_decrease_streak,
   error_history: [...], tasks: {<task_id>: {first_dispatched_at}}}}）。

## 验证
- team-orchestration.md Monitor 段含 sync + 4 判据 + rock-agent-debug + Cron。
- SKILL.md 含 Cron 巡检 + rock-agent-debug 引用。
- grep `rock-agent-debug` 在 rock-eval 内应有命中（之前零引用）。
- grep `Cron` / `sync` 在 Monitor 段命中。
- 不破坏 Phase 2 / 其它角色 / Diagnostician 段。

## 风险
- Cron 是 session 内工具，终端/会话关闭后停止。需在文档写明"Cron 依赖会话存活；
  若需跨会话用 durable:true"。默认是否 durable 待用户确认（见主对话）。
- monitor-state.json 的"3 次不降"等阈值写进 prompt，后续可调。
- rock-agent-debug 深挖较重，已用"可疑才调"约束成本。
