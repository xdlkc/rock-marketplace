# 报告模板 — 深度归因分析

本文件定义三种任务分析报告模板，供 Phase 2 子 agent 根据任务分类选择使用。

任务分类逻辑见 `deep-analysis.md` §1.5。

---

## 模板 A：零分任务深度归因报告

适用条件：`avg_reward == 0` 且无 exception（纯零分任务）。

````markdown
# 零分任务深度归因报告

## §1 基础信息

| 字段 | 值 |
|------|-----|
| Task ID | {task_id} |
| Experiment ID | {experiment_id} |
| Job Name | {job_name} |
| Agent | {agent_name} |
| Model | {model_name} |
| Reward | 0 |
| Trial 数量 | {trial_count} |
| 状态 | {status} |

**快速查看命令：**

```bash
rc agent view -e {experiment_id} -j {job_name} [--pre]
rc agent view -e {experiment_id} -j {job_name} [--pre] --trajectory
rc agent fs ls -e {experiment_id} -j {job_name} [--pre]
rc agent fs cat {trial_name}/result.json -e {experiment_id} -j {job_name} [--pre]
```

## §2 RT 参数分析

| 参数 | 当前值 | 合理性评估 |
|------|--------|------------|
| temperature | {temperature} | <!-- 代码任务建议 ≤0.2；探索性任务可 0.7+ --> |
| top_p | {top_p} | <!-- 通常 0.9-1.0，与 temperature 配合 --> |
| thinking_budget / reasoning_effort | {thinking_budget} | <!-- 复杂推理任务建议 high 或较大 budget --> |
| max_tokens / max_output_tokens | {max_tokens} | <!-- 是否足够完成任务输出 --> |
| override_timeout_sec | {timeout_sec} | <!-- 任务复杂度是否匹配超时时间 --> |
| memory | {memory} | <!-- 是否启用；长对话任务建议启用 --> |
| concurrency | {concurrency} | <!-- 并发数是否合理 --> |

**参数合理性总结**：{parameter_summary}

## §3 资源消耗分析

- **Token 用量**：prompt {prompt_tokens} / completion {completion_tokens} / total {total_tokens}
- **费用**：{cost}
- **执行时长**：{duration_sec}s / 超时上限 {timeout_sec}s（{duration_pct}%）
- **API 调用次数**：约 {api_call_count} 次（根据轨迹步数估算）
- **是否接近资源上限**：{resource_limit_assessment}

## §4 任务目标

- **任务描述**（来自首条 user message）：{task_description}
- **Agent 理解**（来自 reasoning_content）：{agent_understanding}
- **理解是否准确**：{understanding_accuracy}

## §5 完整轨迹摘要

> 注意：对于 100+ 步的长轨迹，重点关注前 20 步 + 后 20 步 + 中间关键转折点。

- Step 1: [{tool_or_action}] - {description} - {result}
- Step 2: [{tool_or_action}] - {description} - {result}
- ...
- Step N: [{tool_or_action}] - {description} - {result}

**关键节点标记：**

- 🔴 **首次偏离正确路径**：Step {deviation_step} — {deviation_description}
- 🟡 **自我纠错尝试**：
  - Step {correction_step_1} — {correction_description_1}
  - Step {correction_step_2} — {correction_description_2}
  - ...（如有多次纠错均列出）
- 🔵 **最终失败点**：Step {final_failure_step} — {final_failure_description}

## §6 失败分类

- **主分类**：{failure_taxonomy_id}（{failure_category_cn}）
- **次分类**：{sub_category}（如有）
- **置信度**：高 / 中 / 低
- **分类依据**：{classification_reasoning}

## §7 关键转折点分析

- **位置**：Step {turning_point_step}
- **发生了什么**：{turning_point_event}
- **为何关键**：{turning_point_significance}
- **Agent 在该点的推理**：{agent_reasoning_at_turning_point}

## §8 根因分析

- **一句话根因**：{root_cause_one_liner}
- **详细归因**：{root_cause_detailed}

## §9 正确路径参考

1. {correct_step_1}
2. {correct_step_2}
3. {correct_step_3}
4. ...

## §10 Verifier 对比

- **Verifier 输出摘要**（test-stdout / test-stderr）：{verifier_output_summary}
- **Agent 最终状态 vs Verifier 期望状态**：{agent_vs_verifier}
- **是否存在 Verifier 误判可能**：{verifier_misjudgment_possibility}

## §11 原始数据附录

- **result.json 关键字段**：
  - duration: {duration}
  - reward_stats: {reward_stats}
  - token_usage: {token_usage}
- **Exception 信息**：无
- **Trial reward 明细**：
  - {trial_1_name}: reward = {trial_1_reward}
  - {trial_2_name}: reward = {trial_2_reward}
  - ...
````

---

## 模板 B：异常任务诊断报告

适用条件：有 exception 且 `avg_reward > 0`（纯异常任务）。

````markdown
# 异常任务诊断报告

## §1 基础信息

| 字段 | 值 |
|------|-----|
| Task ID | {task_id} |
| Experiment ID | {experiment_id} |
| Job Name | {job_name} |
| Agent | {agent_name} |
| Model | {model_name} |
| Reward | {avg_reward} |
| Trial 数量 | {trial_count} |
| **状态** | **{status}（含异常）** |

**快速查看命令：**

```bash
rc agent view -e {experiment_id} -j {job_name} [--pre]
rc agent fs cat {trial_name}/exception.txt -e {experiment_id} -j {job_name} [--pre]
rc agent fs cat {trial_name}/result.json -e {experiment_id} -j {job_name} [--pre]
```

## §2 异常信息

- **exception_type**：{exception_type}
- **exception_message**：{exception_message}
- **异常发生阶段**：{exception_phase}
  <!-- 可选值：agent执行中 / verifier阶段 / 沙箱启动阶段 / 环境构建阶段 -->
  <!-- 判断方法：检查 result.json 中哪个阶段出现异常记录 -->

## §3 异常根因分析

- **异常层级**：{exception_level}
  <!-- infra_error：基础设施错误（沙箱调度、网络、存储等） -->
  <!-- env_issue：环境问题（依赖缺失、配置错误、权限不足等） -->
- **一句话根因**：{exception_root_cause_one_liner}
- **详细分析**：
  - 为何发生：{why_it_happened}
  - 是否具有系统性（检查同实验其他 job 是否有类似异常）：{systemic_assessment}
  - 影响范围：{impact_scope}

## §4 解决方案

### 4.1 通用建议

参考 failure-taxonomy.md 解决方案映射表。

{general_recommendations}

### 4.2 具体参数调整

| 参数 | 当前值 | 建议值 | 调整原因 |
|------|--------|--------|----------|
| {param_1} | {current_1} | {suggested_1} | {reason_1} |
| {param_2} | {current_2} | {suggested_2} | {reason_2} |
| ... | ... | ... | ... |

### 4.3 处置判断

- ✅ **调参后可 retry**：原因明确且可通过参数调整解决时选此项
- ⚠️ **需人工介入**：涉及环境配置/权限/网络策略等需人工处理时选此项
- 🐛 **平台 bug 需上报**：平台 API 500/沙箱调度异常等平台侧问题时选此项

**选择**：{disposition_icon} — {disposition_reason}

## §5 原始数据附录

- **exception.txt 完整内容**：
```
{exception_txt_content}
```
- **result.json 关键字段**：
  - duration: {duration}
  - reward_stats: {reward_stats}
  - token_usage: {token_usage}
- **相关日志片段**：
```
{related_log_snippets}
```
````

---

## 模板 C：零分+异常任务综合诊断报告

适用条件：`avg_reward == 0` 且有 exception（零分+异常合并）。

合并原则：先分析异常（优先级更高），再分析轨迹（若异常在 agent 执行前发生则跳过轨迹部分）。

````markdown
# 零分+异常任务综合诊断报告

## §1 基础信息

| 字段 | 值 |
|------|-----|
| Task ID | {task_id} |
| Experiment ID | {experiment_id} |
| Job Name | {job_name} |
| Agent | {agent_name} |
| Model | {model_name} |
| Reward | 0 |
| Trial 数量 | {trial_count} |
| 状态 | {status} |
| **特征** | **零分 + 异常并存** |

**快速查看命令：**

```bash
rc agent view -e {experiment_id} -j {job_name} [--pre]
rc agent view -e {experiment_id} -j {job_name} [--pre] --trajectory
rc agent fs ls -e {experiment_id} -j {job_name} [--pre]
rc agent fs cat {trial_name}/result.json -e {experiment_id} -j {job_name} [--pre]
rc agent fs cat {trial_name}/exception.txt -e {experiment_id} -j {job_name} [--pre]
```

---

### — 异常分析部分 —

## §2 异常信息

- **exception_type**：{exception_type}
- **exception_message**：{exception_message}
- **异常发生阶段**：{exception_phase}
  <!-- 可选值：agent执行中 / verifier阶段 / 沙箱启动阶段 / 环境构建阶段 -->
  <!-- 判断方法：检查 result.json 中哪个阶段出现异常记录 -->

## §3 异常根因分析

- **异常层级**：{exception_level}
  <!-- infra_error：基础设施错误（沙箱调度、网络、存储等） -->
  <!-- env_issue：环境问题（依赖缺失、配置错误、权限不足等） -->
- **一句话根因**：{exception_root_cause_one_liner}
- **详细分析**：
  - 为何发生：{why_it_happened}
  - 是否具有系统性（检查同实验其他 job 是否有类似异常）：{systemic_assessment}
  - 影响范围：{impact_scope}
- **异常是否为零分的直接原因**：是 / 否
  - 若**是**：零分完全由异常导致，轨迹分析仅供参考
  - 若**否**：异常与零分有独立成因，需分别归因

## §4 异常解决方案

### 4.1 通用建议

参考 failure-taxonomy.md 解决方案映射表。

{general_recommendations}

### 4.2 具体参数调整

| 参数 | 当前值 | 建议值 | 调整原因 |
|------|--------|--------|----------|
| {param_1} | {current_1} | {suggested_1} | {reason_1} |
| {param_2} | {current_2} | {suggested_2} | {reason_2} |
| ... | ... | ... | ... |

### 4.3 处置判断

- ✅ **调参后可 retry**：原因明确且可通过参数调整解决时选此项
- ⚠️ **需人工介入**：涉及环境配置/权限/网络策略等需人工处理时选此项
- 🐛 **平台 bug 需上报**：平台 API 500/沙箱调度异常等平台侧问题时选此项

**选择**：{disposition_icon} — {disposition_reason}

---

### — 轨迹分析部分 —

> 注意：若 §3 判定异常为零分直接原因且异常发生在 agent 执行之前，§5-§12 标注"不适用——异常发生在 agent 执行之前"并跳至 §13。

## §5 RT 参数分析

| 参数 | 当前值 | 合理性评估 |
|------|--------|------------|
| temperature | {temperature} | <!-- 代码任务建议 ≤0.2；探索性任务可 0.7+ --> |
| top_p | {top_p} | <!-- 通常 0.9-1.0，与 temperature 配合 --> |
| thinking_budget / reasoning_effort | {thinking_budget} | <!-- 复杂推理任务建议 high 或较大 budget --> |
| max_tokens / max_output_tokens | {max_tokens} | <!-- 是否足够完成任务输出 --> |
| override_timeout_sec | {timeout_sec} | <!-- 任务复杂度是否匹配超时时间 --> |
| memory | {memory} | <!-- 是否启用；长对话任务建议启用 --> |
| concurrency | {concurrency} | <!-- 并发数是否合理 --> |

**参数合理性总结**：{parameter_summary}

## §6 资源消耗分析

- **Token 用量**：prompt {prompt_tokens} / completion {completion_tokens} / total {total_tokens}
- **费用**：{cost}
- **执行时长**：{duration_sec}s / 超时上限 {timeout_sec}s（{duration_pct}%）
- **API 调用次数**：约 {api_call_count} 次（根据轨迹步数估算）
- **是否接近资源上限**：{resource_limit_assessment}

## §7 任务目标

- **任务描述**（来自首条 user message）：{task_description}
- **Agent 理解**（来自 reasoning_content）：{agent_understanding}
- **理解是否准确**：{understanding_accuracy}

## §8 完整轨迹摘要

> 注意：对于 100+ 步的长轨迹，重点关注前 20 步 + 后 20 步 + 中间关键转折点。

- Step 1: [{tool_or_action}] - {description} - {result}
- Step 2: [{tool_or_action}] - {description} - {result}
- ...
- Step N: [{tool_or_action}] - {description} - {result}

**关键节点标记：**

- 🔴 **首次偏离正确路径**：Step {deviation_step} — {deviation_description}
- 🟡 **自我纠错尝试**：
  - Step {correction_step_1} — {correction_description_1}
  - Step {correction_step_2} — {correction_description_2}
  - ...（如有多次纠错均列出）
- 🔵 **最终失败点/异常中断点**：Step {final_failure_step} — {final_failure_description}

## §9 失败分类

- **主分类**：{failure_taxonomy_id}（{failure_category_cn}）
- **次分类**：{sub_category}（如有）
- **置信度**：高 / 中 / 低
- **分类依据**：{classification_reasoning}

## §10 关键转折点分析

- **位置**：Step {turning_point_step}
- **发生了什么**：{turning_point_event}
- **为何关键**：{turning_point_significance}
- **Agent 在该点的推理**：{agent_reasoning_at_turning_point}
- **与异常的关系**：{relation_to_exception}

## §11 根因分析

- **一句话根因**（综合异常与轨迹）：{combined_root_cause_one_liner}
- **详细归因**：{combined_root_cause_detailed}

## §12 正确路径参考

> 在无异常的理想环境下：

1. {correct_step_1}
2. {correct_step_2}
3. {correct_step_3}
4. ...

## §13 Verifier 对比

- **Verifier 输出摘要**（test-stdout / test-stderr）：{verifier_output_summary}
- **Agent 最终状态 vs Verifier 期望状态**：{agent_vs_verifier}
- **是否存在 Verifier 误判可能**：{verifier_misjudgment_possibility}
- **是否因异常导致 verifier 未运行**：{verifier_skipped_due_to_exception}

## §14 原始数据附录

- **exception.txt 完整内容**：
```
{exception_txt_content}
```
- **result.json 关键字段**：
  - duration: {duration}
  - reward_stats: {reward_stats}
  - token_usage: {token_usage}
- **Trial reward 明细**：
  - {trial_1_name}: reward = {trial_1_reward}
  - {trial_2_name}: reward = {trial_2_reward}
  - ...
````

---

## 模板选择指南

| 任务特征 | 使用模板 | 报告标题前缀 |
|----------|----------|--------------|
| reward=0，无 exception | 模板 A | "零分任务深度归因报告" |
| 有 exception，reward>0 | 模板 B | "异常任务诊断报告" |
| reward=0，有 exception | 模板 C | "零分+异常任务综合诊断报告" |
| 0 < reward < 1，无 exception | 现有模板 | "Task:"（沿用 deep-analysis.md Step D 原有模板） |

> 注意：部分完成任务（0 < reward < 1 且无异常）继续使用 deep-analysis.md 中的现有模板。
