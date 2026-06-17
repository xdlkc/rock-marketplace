---
name: rock-eval
description: 使用 rockcli（rc）对 AI Agent 做批量回归评估：在数据集上跑分、生成报告、排查与重试失败用例。当用户要跑 benchmark / regression / agent eval、查看 reward 与通过率，或对一批任务的评估结果做分析时使用。
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
├─ Tasks stuck in "dispatched" ───────→ Section 3: Sync
├─ Understand why tasks failed ───────→ Section 4: Diagnose
├─ Rerun failed tasks ────────────────→ Section 5: Retry
├─ Manual rc commands ────────────────→ Read references/rockcli-cheatsheet.md
├─ Full regression, worried about context bloat
│   (long run + multi-failure triage) → Read references/team-orchestration.md
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
| `--window-size` | **Global concurrency cap** — a sliding window that keeps N tasks in flight at all times: the moment one finishes, the next starts. Recommended cap is **~10** (shared ROCKCLI quota — higher values risk rate-limiting and impacting other users; the script imposes no hard cap). `0` = no limit (all tasks in parallel) |
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
| `references/data-formats.md` | User asks about result JSON structure, report data format, task fields, exception types, or wants to parse/script against result files |
| `references/team-orchestration.md` | Full regression expected to be long with multi-failure triage — coordinate Runner / Reporter / Diagnostician subagents so the main context only holds conclusions, not raw logs/trajectories |
| `scripts/regression.py` | The main script — run it, don't read it into context (2000+ lines) |

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
