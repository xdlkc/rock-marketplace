# rock-eval: 把模型配置纳入 alignment baseline 可比性维度

> 日期 2026-06-17。基于 1.4.0（commit 01a2a9c）。根因：alignment baseline 只覆盖
> bench/dataset/split/agent/model/image/cluster/ee/set，**不含** temperature/thinking/
> reasoning/max_tokens/timeout，"配置交叉检查"也不查它们 → 即使其它维度全对齐，
> 采样/推理配置不同仍会导致 pass rate 不可比 = 白跑。

## 用户决策（已拍板）
1. 模型配置 → **纳入 baseline + 强制 drift 检查**
2. 调研/回归顺序 → **保持现状**（Phase 1.5 已串行）
3. 运行环境 → 1.4.0，alignment 流程可用

## 改动范围（都在 01a2a9c 动过的 3 个文件 + 可能的新增 1 个）

### A. data-formats.md（核心 schema 改动）
位置：`plugins/rock/skills/rock-eval/references/data-formats.md:235-261`（jsonc 示例）+ `:271-273`（字段说明表）

- 在 `reference_config` 的 jsonc 示例里新增一个对象字段 `sampling`（或 `model_config`），
  收纳与"分数可比性"直接相关的采样/推理参数：
  - `temperature`
  - `top_p`（可选）
  - `thinking` / `reasoning_effort`（extended thinking 等级，写明类型，如 "high"/"none"/数值）
  - `max_tokens`
  - `timeout`（**单 task 推理超时**，注意与现有 `--poll-timeout` 调度超时区分，文案写清楚）
- 字段说明表新增 `reference_config.sampling.*` 行，标注：未知/未公开的字段填 `null`，
  不得省略（保证对比时不被当成"未检查"）。
- 命名约定不动。

### B. SKILL.md（流程里把模型配置列入强制检查）
位置：`SKILL.md:125-132`（主流程"配置交叉检查"drift 点清单）+ `:356-368`（FAQ）

- 在主流程 drift 点清单里新增条目：**采样/推理配置（temperature / thinking / max_tokens / 超时），
  参考来源是否公开这些值；若公开而本次 run 未对齐，pass rate 可能不可比**。
- 措辞从"标出不一致并告知"维持，但因 data-formats 已纳入字段，这里点名这些维度。
- FAQ 第 3 步同步补充：配置交叉检查除 model/image/split/env 外，还要核对采样/推理参数。
- **不改顺序**，不动 Phase 1.5 串行结构。

### C. team-orchestration.md（Diagnostician 对比逻辑强化）
位置：`team-orchestration.md:49-54`（Phase 1.5）+ `:189-219`（Diagnostician alignment prompt）

- Phase 1.5 第 52 行"配置交叉检查"补一句：**含采样/推理参数**。
- Diagnostician prompt 第 204/209 行配置对比逻辑强化为：
  - 对比 `reference_config` 全字段（**含 `sampling.*`**）vs `configs/<EXP_ID>.json`；
  - 实际配置里采样参数可能藏在三处，需逐一解出：
    1. `model`（字符串，本身不是采样参数，但要核对版本）
    2. `set`（path=value 列表）—— 解析其中 temperature/thinking/max_tokens 等键
    3. `config`（JobConfig YAML **路径**，内容不在 JSON 内）—— **必要时 cat/读取该 YAML**
       提取采样字段；regression.py 不解析它，Diagnostician 需自己读
  - 若 `sampling.*` 任一字段在参考里已知、但实际配置无法确认 → 报"无法验证可比性"而非静默通过。
  - 回报格式"配置差异"项明确要求列出 sampling 差异。

### D. （可选）无代码改动
regression.py **不改**。模型配置仍只能经 --set / --config 注入，SAVE_FIELDS 已快照 model/set/config。
唯一缺口是 `config` 指向的 YAML 内容不进 configs JSON——由 Diagnostician 按需读取弥补（C 处理）。

## 验证
- data-formats.md jsonc 示例仍合法（jsonc 注释）。
- 三个文件互相引用的字段名一致（`sampling` / 字段命名统一）。
- 不破坏 Phase 1.5 串行结构。
- grep `temperature|thinking|max_tokens|timeout` 在 alignment 上下文应命中。

## 风险
- `sampling` 字段名 vs rc/rockcli 实际 YAML 路径命名差异：实现时以 data-formats 示例为准，
  Diagnostician prompt 里说明"实际键名以 configs/config YAML 里 rc 真实路径为准，做近似匹配"。
