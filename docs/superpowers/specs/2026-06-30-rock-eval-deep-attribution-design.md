# Rock-Eval 实验任务深度归因优化设计

> 状态：已确认  
> 日期：2026-06-30  
> 作者：keluo  

---

## 背景

rock-eval 现有的 `deep-analysis.md` 定义了 3 阶段分析流程（概览 → 并行深度分析 → 模式聚合），`failure-taxonomy.md` 有 8 类失败分类。但现有实现对零分任务和异常任务的处理粒度不足：

- 零分任务没有基于原始模型轨迹 + RT 参数的结构化详细报告
- 异常任务缺少明确的根因归类和可操作的解决方案

---

## 需求

### 零分任务

- 基于原始模型轨迹 + RT 参数，输出包含完整轨迹摘要（标注关键节点）、参数分析、资源消耗、verifier 对比的详细报告
- 轨迹处理方式：完整轨迹摘要 + 关键节点标注（首次偏离 🔴、自我纠错 🟡、最终失败点 🔵）

### 异常任务

- 定义范围：仅 infra/env 层异常（有 exception 的任务），如 API 超时、沙箱 OOM、网络不通
- 输出三级解决方案：通用建议 → 具体参数调整值 → retry/人工介入/上报判断

### 重叠处理

- 零分 + 异常合并为一份报告，同时包含异常根因分析和轨迹归因

### 输出格式

- 每个任务一个 `.md` 文件，沿用现有 `/tmp/bench-analysis-<EXP_ID>/` 目录模式

---

## 方案选择

采用 **方案 A：增强现有参考文档指引**。改动集中在 `references/` 文档层，不涉及脚本代码改动。

理由：

1. 核心分析工作本质上是 LLM 驱动的，脚本层能做的主要是数据采集，现有 `rc` 命令已足够
2. 改动最小，风险最低
3. 通过精确的报告模板和 checklist 可有效约束 LLM 输出质量

---

## 任务分类逻辑

在 Phase 2 分派子 agent 之前，将需要深度分析的任务分为三类：

| 类型 | 判定条件 | 分析侧重 |
|------|----------|----------|
| 纯零分任务 | reward=0 且无 exception | 轨迹归因 + RT 参数 + 资源消耗 + verifier 对比 |
| 纯异常任务 | 有 exception 且 reward>0 | infra 根因 + 解决方案三级 |
| 零分 + 异常 | reward=0 且有 exception | 合并报告：先异常根因（优先级更高），再轨迹分析（标注被异常中断的点） |

非零分、非异常但 reward<1.0 的任务（partial_completion）沿用现有 `deep-analysis.md` 分析流程不变。

---

## 报告模板

### 零分任务报告模板

```markdown
# 零分任务深度归因报告: {task_name}

## 1. 基础信息
- 任务ID / 实验ID / Agent / Model
- reward / 试验次数 / 完成次数

## 2. RT 参数分析
- 当前参数：temperature / top_p / thinking_budget / max_tokens / inference_timeout / memory / concurrency
- 参数合理性评估：逐项分析各参数是否适配该任务类型

## 3. 资源消耗分析
- token 用量（input/output/total）
- cost
- 执行时长 vs inference_timeout（是否接近超时）
- API 调用次数

## 4. 任务目标
- 任务描述（首条 user message 摘要）
- agent 对任务的理解（从 reasoning 中提取）

## 5. 完整轨迹摘要
按步骤编号列出 agent 的每个动作：
- Step N: [工具/动作] - [简要描述] - [结果]
关键节点标注：
- 🔴 首次偏离正确路径
- 🟡 自我纠错尝试
- 🔵 最终失败点

## 6. 失败分类
- 主分类：{failure_taxonomy 中的类别}
- 次分类（如有）
- 置信度：高/中/低

## 7. 关键转折点分析
- 转折点位置：Step N
- 发生了什么
- 为什么这是关键
- agent 当时的 reasoning

## 8. 根因分析
- 一句话根因
- 详细归因

## 9. 正确路径参考
- 该任务的合理解题路径

## 10. Verifier 对比
- verifier 判零分的具体输出（test-stdout/test-stderr）
- agent 最终提交的状态 vs verifier 期望的状态
- 是否存在 verifier 误判的可能

## 11. 原始数据附录
- result.json 关键字段
- exception 信息（如有）
```

### 异常任务报告模板

```markdown
# 异常任务诊断报告: {task_name}

## 1. 基础信息
- 任务ID / 实验ID / Agent / Model
- reward / 状态 / 试验次数

## 2. 异常信息
- exception_type
- exception_message
- 异常发生的阶段（agent 执行中 / verifier 阶段 / 沙箱启动阶段）

## 3. 异常根因分析
- 异常层级：infra_error / env_issue
- 一句话根因
- 详细分析：为什么发生、是否为系统性问题

## 4. 解决方案

### 4.1 通用建议
### 4.2 具体参数调整（当前值 → 建议值 + 原因）
### 4.3 处置判断
- ✅ 调参后可 retry
- ⚠️ 需人工介入
- 🐛 平台 bug 需上报

## 5. 原始数据附录
- exception.txt 内容
- result.json 关键字段
- 相关日志片段
```

### 零分 + 异常合并报告模板

结构为：

1. **§1 基础信息合并**
2. **§2–§4 异常报告**（异常信息 + 根因 + 解决方案）
3. **§5–§13 零分报告**（RT 参数 + 资源消耗 + 任务目标 + 轨迹摘要 + 失败分类 + 转折点 + 根因 + 正确路径 + verifier 对比）
4. **§14 原始数据附录合并**

标题改为：

```
# 零分+异常任务综合诊断报告: {task_name}
```

---

## 文件修改范围

### 新增文件

| 文件 | 说明 |
|------|------|
| `references/report-templates.md` | 定义三种报告模板，供 Phase 2 子 agent 引用 |

### 修改文件

#### 1. `references/deep-analysis.md`

- **Phase 1 末尾**：增加任务三分类逻辑，替代当前简单的 "needs_analysis" 二分法
- **Phase 2 子 agent 指引**：根据任务类型选择对应报告模板
- **Phase 2 数据采集步骤**：增加 RT 参数获取和资源消耗数据采集

#### 2. `references/failure-taxonomy.md`

- 为 `env_issue` 和 `infra_error` 增加「解决方案映射表」
- 列出常见异常类型对应的通用建议、参数调整方向、处置判断

#### 3. `references/schemas.json`（可选增量优化）

- TeamCreate 模式适配：更新 `DiagnoseOutput` schema 增加 `solution_level` 等字段

### 不修改的文件

- `scripts/` 下的 Python 脚本
- `SKILL.md` 入口
- 其他 `references` 文档
