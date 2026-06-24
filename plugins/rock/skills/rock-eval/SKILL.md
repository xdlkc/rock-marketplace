---
name: rock-eval
description: 使用 rockcli（rc）对 AI Agent 做批量回归评估：在数据集上跑分、生成报告、排查与重试失败用例、深度分析失败原因。当用户要跑 benchmark / regression / agent eval、查看 reward 与通过率、对一批任务的评估结果做分析、深度分析失败原因、做 trajectory 分析或 post-mortem 时使用。
---

# Rock Eval — AI Agent Regression Evaluation

This skill orchestrates full regression evaluations for AI agents using `rockcli` (CLI tool, alias `rc`) and the `regression.py` script. It covers the complete lifecycle: dispatching tasks, monitoring progress, analyzing results, diagnosing failures, and retrying.

## When to Use

- User wants to run agent evaluations / benchmarks / regressions
- User asks about evaluation results, pass rates, reward scores
- User wants to troubleshoot failed evaluation tasks
- User wants to retry specific failed tasks
- User references `rc`, `rockcli`, `regression.py`, experiment IDs, or result JSON files
- User asks about benchmark datasets, splits, or task lists

## Quick Start Decision Tree

```
What does the user want to do?
│
├─ Run a new regression ──────────────→ Section 1: Run
├─ Check results / get a report ──────→ Section 2: Report
├─ Tasks stuck in "dispatched" ───────→ Section 3: Sync (full regression: Monitor 用 Cron 每 3 分钟定时 sync+判可疑，可疑时调 rock-agent-debug 确认，见 references/team-orchestration.md § Monitor)
├─ Understand why tasks failed ───────→ Section 4: Diagnose
├─ Rerun failed tasks ────────────────→ Section 5: Retry
├─ 深度分析失败原因 ──────────────────→ Section 6: Analyze（→ references/deep-analysis.md）
├─ 在沙箱内执行回归（内网/长跑隔离）──→ Section 7: Sandbox Run
├─ Manual rc commands ────────────────→ Read references/rockcli-cheatsheet.md
├─ Need ROCK Harbor Job config YAML / agent kwargs
│   → Read references/harbor-config-manual.md
├─ Full regression (long run + multi-failure triage)
│   → Choose orchestration mode:
│     • TeamCreate (recommended for long runs / cross-session resume):
│         Read references/team-orchestration-teamcreate.md
│         (TaskList state machine + structured output schemas in references/schemas.json)
│     • Legacy v2 prompt-driven (single-session, quick setup):
│         Read references/team-orchestration.md (7 角色并行 pipeline)
│   → Do NOT mix modes in one regression.
├─ Need to adjust params after failures (stop/destroy/retry loop)
│   → Read references/team-orchestration.md § Operator (legacy)
│      or references/team-orchestration-teamcreate.md § task-11 (TeamCreate)
└─ Full SOP / workflow reference ─────→ Read references/sop.md
```

## Core Workflow

```
run  ──→  report  ──→  sync (if needed)  ──→  diagnose  ──→  retry
 ^                                                             │
 └─────────────────────────────────────────────────────────────┘
```

The script lives at `scripts/regression.py` relative to this skill's directory. **Run it in place via its absolute path — do not copy it into the user's working directory.** Throughout the commands below, substitute the full path to this skill's `scripts/regression.py`. Output (`results/`, `logs/`, `configs/`) is written relative to wherever you invoke it (typically the user's working directory), so run the commands from the directory where you want results to land.

---

## 1. Run — Dispatch Regression Tasks

Launches all tasks from a dataset against a specified agent, with concurrent execution.

```bash
python3 regression.py run \
  --bench <BENCH> \
  --dataset <DATASET> \
  --split <SPLIT> \
  --agent <AGENT> \
  --concurrency <N> \
  --window-size <N>
```

### Required arguments

| Arg | Purpose |
|-----|---------|
| `--bench` | Bench template — run `rc agent run --help` for current values |
| `--agent` | Agent name — run `rc agent run --help` for current values |
| `--window-size` | **Global concurrency cap** — a sliding window that keeps N tasks in flight at all times: the moment one finishes, the next starts. The appropriate value depends on actual resource/quota conditions — **confirm with the user before dispatching** (higher values risk rate-limiting and impacting other users; the script imposes no hard cap). `0` = no limit (all tasks in parallel) |
| `--concurrency` | *(compat alias)* same meaning as `--window-size`; if both are given, the smaller value wins |

`--window-size`/`--concurrency` cap how many tasks run at once — there is no batch barrier, so throughput stays at the cap for the whole run. `--dataset` and `--split` are required unless `--tasks` is specified.

### Resolving the task list when the user only gives a bench name

If the user provides a bench name but no `--dataset`/`--split`, **do not guess** —
resolve the dataset from the bench template first:

1. Run `rc agent bench getconfig <BENCH> --raw` and read the `datasets` field. It
   gives the dataset `name`, `registry.split`, and `task_names`.
2. Get the task list with `rc datasets <NAME> tasks --split <SPLIT>`, then pass the
   dataset/split to `regression.py run` (or pass the task list via `--tasks`).
3. **Fallback** — some benches don't support the `tasks` subcommand (the dataset
   returns nothing). In that case, use the `task_names` embedded in the template's
   `--raw` output as the task source. Don't assume; actually inspect the `--raw`
   output to decide.

> Harbor-based benches (e.g. `harborframework/*`) always carry `datasets.name` in
> their template, so step 1-2 works for them reliably. See
> `references/rockcli-cheatsheet.md` for the exact commands and YAML shape.

### Agent / bench values — query them live, don't hardcode

The set of supported agents and benches changes as rockcli upgrades. **Do not rely
on a hardcoded list** — run `rc agent run --help` to see the currently supported
`--agent` and `--bench` values (the "常用取值" section), and use those. Bench
templates can also be refreshed with `rc agent deps sync benchhub`.

Two `--agent` values are **stable baselines** whose meaning doesn't change between
versions:

| Agent | Meaning |
|-------|---------|
| `oracle` | Upper-bound baseline — submits the correct answer; validates the scoring/reward chain |
| `nop` | Lower-bound baseline — does nothing; validates dispatch + image/cluster/sandbox setup |

> ⚠️ **Before launching any full regression with a real agent, ask the user whether
> to first run a small `oracle` and/or `nop` smoke check** (a few `--tasks` at low
> concurrency) to verify the environment — scoring chain via `oracle` (reward ≈ full),
> dispatch/image/cluster via `nop` (reward ≈ 0). This catches environment problems
> before they fail the whole batch. See `references/sop.md` for the procedure.

### Alignment baseline — 对齐分数场景（可选步骤）

> 在 oracle/nop 冒烟验证之后、全量 run 之前，**询问用户**：
> "这次回归的目标是对齐/复现已知分数吗？"

如果用户回答**是**（目标是 reproduce/align 某个已发布的 pass rate）：

1. **获取参考分数**：
   - 用户直接提供（per-task reward 或 aggregate pass rate）→ 直接使用
   - 用户提供来源线索（leaderboard URL / paper / 官方网站）→ agent 搜索并提取分数
   - 两者都无 → 提示用户提供来源，否则跳过对齐步骤

2. **配置交叉检查**：
   将用户本次 run 的配置（bench / agent / model / image / cluster / 环境变量等）与
   参考来源使用的配置进行比对。**标出任何不一致**并告知用户——这些差异可能导致分数无法
   对齐。常见差异点：
   - model 版本不同
   - image 版本不同（评分器版本升级可能影响 reward）
   - split 不同（任务集不同则 pass rate 不可比）
   - 环境变量差异（API endpoint、超时设置等）
   - 采样/推理配置（temperature / top_p / thinking（含 reasoning 等级） / max_tokens / 推理超时）：参考来源若公开了这些值而本次 run 未对齐，pass rate 不可比；参考来源未公开则标注"采样配置未知，分数可比性受限"

3. **创建对齐基线文件**：
   将参考分数整理为 task 粒度的 baseline 文件，存放于：
   ```
   baselines/<benchmark-name>-<identifier>.json
   ```
   格式见 `references/data-formats.md` § 对齐基线文件。

4. **告知用户**：baseline 已创建，后续 Diagnostician 可自动对比实际结果 vs 预期，
   定位 score gap 的具体 task 和可能原因。

> 如果用户回答**否**（纯探索性回归，无预期分数），跳过此步骤，直接进入全量 run。

### Pass-through arguments — confirm with the user first

Environment/runtime parameters such as image, cluster, agent, model, and resource
specs are **passed through to `rc agent run` exactly as the user specifies**. Do
**not** assume or inject any default values for these — before dispatching, ask the
user which ones they want to set, and only pass the flags they provide.

> **`--model` is optional.** If omitted, the run uses the model shared by ROCKCLI —
> no need to set it unless the user wants a specific model.

Supported pass-through flags: `--image`, `--cluster`, `--model`, `--ee KEY=VALUE`, `--set path=value`, `--pre`/`--no-pre`, `--namespace`, `--cpus`, `--memory`, `--with-companion`, `--config`, `--async-mode`, `--user-id`, `--base-url`, `--api-key`.

### Control arguments

| Arg | Purpose |
|-----|---------|
| `--resume` | Skip tasks already marked success or error |
| `--tasks t1,t2,...` | Run specific tasks only (dataset/split optional) |
| `--poll-interval` | Seconds between status checks (default 10) |
| `--poll-timeout` | Max wait per task in seconds (default 600) |

### Configuration persistence (save / reuse run configs)

Every `run` and `retry` **automatically** snapshots the full effective configuration to
`configs/<experiment-id>.json` (alongside `results/` and `logs/`) so each regression is
reproducible and traceable. Two flags let you also save to / load from a custom path:

```bash
# Save the current config to a reusable template
python3 regression.py run --bench <BENCH> --agent <AGENT> ... \
  --save-config ./my-template.json

# Later, run from that template — CLI flags override the JSON's values
python3 regression.py run --from-config ./my-template.json \
  --concurrency 8          # only this overrides the file; rest comes from JSON
```

| Flag | Behavior |
|------|----------|
| `--save-config <path>` | Additionally save the effective config to `<path>` (template reuse) |
| `--from-config <path>` | Load `<path>` as the base config; any CLI flag you pass overrides the matching JSON field |

**Merge semantics:** JSON is the base; CLI flags override. A flag you pass on the command line
wins; a field you omit is taken from the JSON. (`--bench`/`--agent` are no longer required on the
CLI when they come from the file.)

The JSON contains the full run parameter set (bench/dataset/split/agent, all pass-through
params, tasks, concurrency/window, poll settings) — **not** the experiment id, which is
regenerated per run. Note `--config` (rc's JobConfig YAML) is a different, pre-existing flag.

### Output

- Result JSON: `results/<experiment-id>.json`
- Config snapshot: `configs/<experiment-id>.json`
- Task logs: `logs/<experiment-id>/<task-id>.log`

---

## 2. Report — View Results

```bash
# Latest experiment, text format
python3 regression.py report

# Specific experiment
python3 regression.py report <EXPERIMENT_ID>

# HTML dashboard (auto-open browser)
python3 regression.py report --format html --open

# JSON for scripting
python3 regression.py report --format json
```

The HTML report is self-contained (~54KB), dark theme, with:
- KPI cards (total/success/error/dispatched + pass rate)
- Donut chart (status distribution)
- Reward histogram (only non-zero bins shown)
- Exception grouping table (deduplicated messages)
- Interactive task table (search, filter by status, sortable columns)

---

## 3. Sync — Refresh Stale States

When tasks are stuck in "dispatched" (timeout or interruption), sync pulls the latest state from the server.

```bash
python3 regression.py sync [EXPERIMENT_ID]
python3 regression.py sync --dry-run          # preview without writing
python3 regression.py sync --force            # re-sync all tasks
```

Always run sync before generating a report if the run was interrupted.

### Monitor 巡检机制（长跑时）

在 agent team 全量长跑场景下（见 `references/team-orchestration.md` § Monitor），巡检角色
用 **Cron 工具每 3 分钟 session-only 定时**做一次完整巡检：

1. `sync` 拉远端真实进展 → 2. `report --format json` 汇总 → 3. 维护
   `logs/<EXP_ID>/monitor-state.json` → 4. 按 4 条判据（dispatched 连续 ≥3 次不降 / error 堆积 /
   pass rate 远低于预期 / 单 task 超过推理超时 1.5 倍）判是否"假执行"。
5. **可疑时才**调用 `rock-agent-debug`（提供 experiment_id + job_name）拉 trial 级真实状态
   确认实际进展；正常则不调，避免无谓深挖。
6. run 结束后用 CronDelete 清理该巡检 Cron。

> ⚠️ **Cron 为 session-only**：巡检依赖当前会话存活，会话/终端关闭则定时巡检停止
> （不会跨会话持久化）。长跑如需跨会话，需用 `durable: true`（默认不开）。

---

## 4. Diagnose — Failure Triage

### Overview mode — see the big picture

```bash
python3 regression.py diagnose [EXPERIMENT_ID]
python3 regression.py diagnose --status error
python3 regression.py diagnose --exception RuntimeError
```

Shows: exception types grouped by count, deduplicated error messages (variable parts normalized), dispatched task list.

### Single-task mode — deep dive

```bash
python3 regression.py diagnose --task <TASK_ID>                    # metadata + local log
python3 regression.py diagnose --task <TASK_ID> --remote           # + server logs
python3 regression.py diagnose --task <TASK_ID> --trajectory       # + execution trace
python3 regression.py diagnose --task <TASK_ID> --artifacts        # + output files
python3 regression.py diagnose --task <TASK_ID> --tail 50          # last 50 lines of local log
```

---

## 5. Retry — Rerun Failed Tasks

Different from `--resume`: retry creates a new experiment and only skips successes.

```bash
# Retry all failed (error + dispatched)
python3 regression.py retry [EXPERIMENT_ID] \
  --bench <BENCH> --agent <AGENT> --concurrency <N> --window-size <N>

# Only error tasks
python3 regression.py retry --filter error ...

# Only specific exception type
python3 regression.py retry --filter error --exception-type RewardFileNotFoundError ...

# Specific tasks
python3 regression.py retry --tasks t1,t2,t3 ...
```

| | `run --resume` | `retry` |
|---|---|---|
| Skips | success + error | success only |
| Experiment ID | reuses original | new (with `retry_of` reference) |
| Filtering | none | by status, exception type, manual list |

`retry` supports the same **configuration persistence** flags as `run` — it auto-saves to
`configs/<new-experiment-id>.json` and accepts `--save-config` / `--from-config` with identical
merge semantics (JSON base, CLI overrides). See Section 1.

---

## Section 6: Analyze — 深度失败分析

对已完成实验做系统性 trajectory 分析，逐任务定位失败根因，产出 per-task 分析报告和汇总摘要。

**适用场景**：用户给出实验 ID，想深入了解为什么某些任务失败——不仅是"错了什么"，而是"为什么错"。

**完整指南**：读取 `references/deep-analysis.md`，其中包含三阶段工作流：

| Phase | 做什么 | 输出 |
|-------|--------|------|
| 1. 实验概览 | 用 `live-score.py` 获取全量数据 | `overview.json` |
| 2. 并行深度分析 | 每批 5-8 个子 agent 分析失败 job 的 trajectory | 每个 task 一个 `.md` 分析文件 |
| 3. 模式聚合 | 汇总失败分类分布 + 改进建议 | `SUMMARY.md` |

**快速启动**：

```bash
# Phase 1: 获取概览
python3 scripts/live-score.py -e <EXP_ID> [--pre] --text

# 或使用辅助脚本生成结构化 JSON
python3 scripts/fetch-overview.py <EXP_ID> [--pre] --output /tmp/bench-analysis-<EXP_ID>/overview.json
```

然后按 `references/deep-analysis.md` 的 Phase 2/3 执行深度分析和聚合。

**失败分类体系**：见 `references/failure-taxonomy.md`（8 种分类 + 边界判断指南）。

---

## Section 7: Sandbox Run — 沙箱内执行回归

将回归脚本提交到 ROCK 沙箱中运行，适用于需要内网环境访问或长时间隔离执行的场景。

### 适用场景

- 回归需要访问内网资源（VPC 内的 API、数据库、私有镜像等）
- 单次回归耗时较长（数小时甚至过夜），不想占用本地终端
- 需要更稳定的网络环境（避免本地网络抖动导致任务中断）
- 希望在受控的资源配额下运行（固定 CPU/内存）

### 前置条件

执行前向用户确认以下信息：

| 项目 | 说明 |
|------|------|
| 工号（`--user-id`） | 用于沙箱资源归属，`rc sandbox start` 默认用当前登录账号，通常无需额外传入；如有多账号场景则需确认 |
| `ROCK_API_KEY` | ROCK 平台凭据 |
| `ANTHROPIC_API_KEY` | Anthropic 凭据（如使用 Claude agent） |
| 其他 env var | 询问用户是否有其他需要注入的环境变量 |
| rockcli 版本 | 是否使用 beta 版（正式版 / beta 版安装脚本不同） |
| 集群 | 沙箱所用集群，通常为 `vpc-sg-a`（内网场景），可询问用户确认 |

> **`--cluster` 是全局选项**，必须放在 `rc` 之后、子命令之前：
> `rc --cluster vpc-sg-a sandbox start ...`，**不能**写成 `rc sandbox start --cluster ...`

---

### Step 1 — 启动沙箱

```bash
rc --cluster vpc-sg-a sandbox start \
  --auto-clear 86400 \
  --wait-for-alive \
  --memory 16g \
  --cpus 4
```

> 输出中包含 `SANDBOX_ID`（如 `sb-xxxxxxxx`），后续所有命令均需带上此 ID。

**`sandbox start` 支持的参数（仅这几个，不要传其他参数）：**

| 参数 | 说明 |
|------|------|
| `--image` | 沙箱镜像（可选） |
| `--memory` | 内存配额（如 `16g`） |
| `--cpus` | CPU 核数（如 `4`） |
| `--timeout` | 沙箱超时时间（秒） |
| `--auto-clear` | 自动清理时间（秒），建议设足够长（如 86400 = 24h） |
| `--wait-for-alive` | 阻塞等待沙箱就绪后再返回 |

---

### Step 2 — 安装 rockcli

```bash
# 正式版
rc sandbox <SANDBOX_ID> exec 'bash -c "$(curl -fsSL http://xrl.alibaba-inc.com/install.sh)"'

# beta 版（如用户需要）
rc sandbox <SANDBOX_ID> exec 'bash -c "$(curl -fsSL http://xrl.alibaba-inc.com/install_beta.sh)"'

# 验证安装
rc sandbox <SANDBOX_ID> exec 'rc version'
```

---

### Step 3 — 注入凭据

> ⚠️ **沙箱不支持 `-e` 传入环境变量**，必须通过 `exec` 写入 `~/.bashrc`。

```bash
rc sandbox <SANDBOX_ID> exec 'echo "export ROCK_API_KEY=<KEY>" >> ~/.bashrc'
rc sandbox <SANDBOX_ID> exec 'echo "export ANTHROPIC_API_KEY=<KEY>" >> ~/.bashrc'

# 如有其他 env var，同样方式追加
# rc sandbox <SANDBOX_ID> exec 'echo "export OTHER_KEY=<VALUE>" >> ~/.bashrc'

# 验证凭据生效
rc sandbox <SANDBOX_ID> exec 'source ~/.bashrc && rc agent bench list --pre'
```

---

### Step 4 — 确认回归配置（复用 Section 1 逻辑）

在本机侧按照 Section 1 的流程确认回归参数（bench / dataset / split / agent / concurrency 等），并生成 `--from-config` 所需的配置文件（`--save-config ./my-config.json`）。

> 沙箱内使用 `--from-config` 加载配置，可避免命令行过长或在 exec 中转义复杂参数。

---

### Step 5 — 创建目录并上传文件

```bash
# 创建工作目录结构
rc sandbox <SANDBOX_ID> exec 'mkdir -p /workspace/scripts /workspace/results /workspace/logs /workspace/configs'

# 上传脚本目录（递归）
rc sandbox <SANDBOX_ID> upload --dir <local-scripts-dir> --target-path /workspace/scripts --recursive

# 上传回归配置文件
rc sandbox <SANDBOX_ID> upload --file ./my-config.json --target-path /workspace/my-config.json
```

> `<local-scripts-dir>` 是本机 `regression.py` 所在的 `scripts/` 目录（此 skill 的绝对路径）。

---

### Step 6 — 后台启动回归

> ⚠️ **必须用 `nohup ... &` 后台化**，否则 `exec` 超时断连后回归进程会被杀死。

```bash
rc sandbox <SANDBOX_ID> exec 'source ~/.bashrc && cd /workspace && nohup python3 scripts/regression.py run --from-config /workspace/my-config.json --window-size 10 > /workspace/logs/regression.out 2>&1 &'
```

如需覆盖配置文件中的部分参数，在 `--from-config` 后追加 CLI 参数（CLI 优先级更高）：

```bash
rc sandbox <SANDBOX_ID> exec 'source ~/.bashrc && cd /workspace && nohup python3 scripts/regression.py run --from-config /workspace/my-config.json --window-size 5 --concurrency 5 > /workspace/logs/regression.out 2>&1 &'
```

---

### Step 7 — 监控进度

```bash
# 查看最新日志（最后 50 行）
rc sandbox <SANDBOX_ID> exec 'tail -50 /workspace/logs/regression.out'

# 查看沙箱命令日志
rc sandbox <SANDBOX_ID> log search --log-file command.log -m 30

# 查看回归进程是否存活
rc sandbox <SANDBOX_ID> exec 'pgrep -a python3'
```

若需要长跑巡检，参考 Section 3 中的 Monitor 机制：在沙箱内定期执行 `sync` + `report`，输出写到 `/workspace/logs/` 后再下载分析。

---

### Step 8 — 取回结果

回归完成后，将结果文件下载到本机：

```bash
# 下载结果 JSON（EXP_ID 可从日志输出中获取）
rc sandbox <SANDBOX_ID> download --file /workspace/results/<EXP_ID>.json

# 下载配置快照
rc sandbox <SANDBOX_ID> download --file /workspace/configs/<EXP_ID>.json

# 在本机生成报告（使用 Section 2 的 report 命令）
python3 regression.py report /path/to/<EXP_ID>.json
```

如果不确定 EXP_ID，可先列出结果目录：

```bash
rc sandbox <SANDBOX_ID> exec 'ls /workspace/results/'
```

---

### Step 9 — 停止并清理沙箱

```bash
rc sandbox <SANDBOX_ID> stop
```

> `--auto-clear` 会在指定时间后自动清理，但提前手动 stop 可立即释放资源，**stop 之后文件将无法下载**，务必先完成 Step 8。

---

### 注意事项与常见陷阱

| 陷阱 | 说明 |
|------|------|
| `--cluster` 位置错误 | 必须是 `rc --cluster vpc-sg-a sandbox ...`，不能放在子命令后面 |
| 不加 `nohup &` | exec 连接超时断开后，回归进程会随之终止 |
| 凭据未 `source ~/.bashrc` | `exec` 每次是新的 shell，必须在命令前加 `source ~/.bashrc &&` 才能读到写入的 env var |
| stop 前未下载结果 | 沙箱停止后文件不可访问，先 download 再 stop |
| `sandbox start` 参数传错 | `--env`/`-e` 等不是 `sandbox start` 的合法参数，会报错；只允许 `--image`/`--memory`/`--cpus`/`--timeout`/`--auto-clear`/`--wait-for-alive` |

---

## Experiment ID Resolution

All subcommands accept an optional `experiment` positional argument:

1. **Omitted** — uses the most recently modified file in `results/`
2. **Experiment ID** — matches `results/{id}.json`, then prefix-matches `results/{id}*.json`
3. **File path** — uses the file directly

---

## Bundled Resources

| Path | When to read |
|------|-------------|
| `references/sop.md` | User asks for the full SOP, typical workflows, or detailed parameter reference |
| `references/rockcli-cheatsheet.md` | User needs raw `rc` commands outside of regression.py (manual queries, dataset browsing, sandbox management) |
| `references/harbor-config-manual.md` | User asks how to write ROCK Harbor Job `config.yaml`, `JobConfig` fields, timeout/kwargs semantics, environment kwargs, or per-agent configuration |
| `references/data-formats.md` | User asks about result JSON structure, report data format, task fields, exception types, or wants to parse/script against result files |
| `references/team-orchestration.md` | Full regression with 7-role parallel pipeline — **legacy v2 prompt-driven mode** (single-session). Lead / OracleChecker / NopChecker / Runner / Monitor / Diagnostician / Operator. Coordinate subagents so main context only holds conclusions. Includes Operator loop for stop→destroy→retune→rerun cycles |
| `references/team-orchestration-teamcreate.md` | Full regression — **TeamCreate mode** (recommended for long runs / cross-session resume). Uses CC-native TeamCreate + TaskList state machine + structured output schemas. Currently implements Phase 1-2 (task-1 ~ task-4: config confirm + smoke + decision); Phase 3+ (full run / monitor / diagnose / operator loop) pending |
| `references/schemas.json` | Structured output schemas for TeamCreate mode — `SmokeOutput` (task-2/task-3), `ConfigConfirmOutput` (task-1), `SmokeDecisionOutput` (task-4). Enforced via Agent tool with schema option. Legacy v2 mode does NOT use these schemas |
| `scripts/regression.py` | The main script — run it, don't read it into context (2000+ lines) |
| `references/deep-analysis.md` | 深度失败分析完整指南（三阶段工作流），Section 6 触发时读取 |
| `references/failure-taxonomy.md` | 8 种失败分类定义、识别方法和边界判断指南，深度分析时参考 |

---

## Common Scenarios

### "I want to run a new benchmark"

1. Confirm with the user: bench name, dataset, split, agent, concurrency, and any
   pass-through parameters they need (image, cluster, model, cpus/memory, env vars,
   namespace, pre/prod). Do not assume defaults for these — only pass what the user
   specifies.
2. **Ask whether to first smoke-check the environment with `oracle` / `nop`** on a
   few tasks before the full run (see Section 1). Skip only if the user declines.
3. Run `regression.py run` with the confirmed parameters
4. When done, generate HTML report

### "The run got interrupted"

1. `regression.py sync` to refresh server-side states
2. `regression.py report` to see current status
3. `regression.py run --resume` to continue unfinished tasks

### "Why did tasks fail?"

1. `regression.py diagnose` for overview
2. Pick a representative task from the top exception group
3. `regression.py diagnose --task <ID> --remote --trajectory` for details
4. Suggest fix or retry based on root cause

### "Retry just the Docker failures"

1. `regression.py diagnose --exception RuntimeError` to confirm the set
2. `regression.py retry --filter error --exception-type RuntimeError ...`
3. `regression.py report` on the new experiment

### "How do I see what datasets/agents/benches are available?"

Read `references/rockcli-cheatsheet.md`, then use `rc datasets`, `rc agent bench list`, etc.

### "I want to align/reproduce published scores"（对齐分数场景）

1. 确认对齐目标：哪个 bench/dataset/split，参考来源是什么（leaderboard / paper / 内部历史）
2. 获取参考分数：从来源提取 per-task reward（或至少 aggregate pass rate）
3. 配置交叉检查：对比参考配置 vs 本次配置，标出差异（model / image / split / env vars / 采样与推理参数：temperature · top_p · thinking · max_tokens · 推理超时）
4. 创建 baseline 文件：`baselines/<name>.json`（格式见 `references/data-formats.md` § 对齐基线文件）
5. Oracle/nop 冒烟验证（同标准流程）
6. Run `regression.py run` with confirmed parameters
7. 生成报告 + 派 Diagnostician 做 alignment 对比：
   - 逐 task 比对 actual vs expected reward
   - 配置 drift 分析
   - Top gap tasks + 根因假设
8. 根据 Diagnostician 结论决定下一步（调参 retry / 接受差异 / 报告给用户）
