---
name: rock-eval
description: |
  Run and manage full regression evaluations for AI agents using rockcli (rc) and regression.py.
  Use this skill whenever the user mentions: benchmark, regression, evaluation, agent eval, aone-bench,
  running tasks on a dataset, viewing eval results/reports, diagnosing failures, retrying failed tasks,
  rockcli, rc agent run, reward scores, pass rate, or anything related to AI agent benchmark evaluation.
  Also use when the user references regression.py, result JSON files, experiment IDs, or wants to
  dispatch batch agent tasks against a dataset. Even if they don't say "regression" explicitly but
  describe running an agent across multiple tasks and checking results, this skill applies.
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
└─ Full SOP / workflow reference ─────→ Read references/sop.md
```

## Core Workflow

```
run  ──→  report  ──→  sync (if needed)  ──→  diagnose  ──→  retry
 ^                                                             │
 └─────────────────────────────────────────────────────────────┘
```

The script lives at `scripts/regression.py` relative to this skill's directory. Before first use, either copy it to the user's working directory or run it via absolute path.

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
| `--bench` | Bench template (e.g. `aone-bench`, `SWE-bench`, `terminal-bench-2`) |
| `--agent` | Agent name (e.g. `claude-code`, `swe-agent`, `mini-swe-agent`) |
| `--concurrency` | Max parallel tasks |
| `--window-size` | Sliding window size (`0` = dispatch all at once) |

`--dataset` and `--split` are required unless `--tasks` is specified.

### Optional arguments (pass-through to rockcli)

All `rc agent run` parameters are supported: `--image`, `--cluster`, `--model`, `--ee KEY=VALUE`, `--set path=value`, `--pre`/`--no-pre`, `--namespace`, `--cpus`, `--memory`, `--with-companion`, `--config`, `--async-mode`, `--user-id`, `--base-url`, `--api-key`.

### Control arguments

| Arg | Purpose |
|-----|---------|
| `--resume` | Skip tasks already marked success or error |
| `--tasks t1,t2,...` | Run specific tasks only (dataset/split optional) |
| `--poll-interval` | Seconds between status checks (default 10) |
| `--poll-timeout` | Max wait per task in seconds (default 600) |

### Output

- Result JSON: `results/<experiment-id>.json`
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
| `scripts/regression.py` | The main script — run it, don't read it into context (2000+ lines) |

---

## Common Scenarios

### "I want to run a new benchmark"

1. Confirm: bench name, dataset, split, agent, concurrency
2. Run `regression.py run` with those parameters
3. When done, generate HTML report

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
