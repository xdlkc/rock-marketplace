#!/usr/bin/env python3
"""Live scoring for running ROCK experiments.

Queries the remote platform directly via `rc agent view` and computes
real-time scores at job granularity — including partially-finished
jobs (e.g., 3/5 trials done).

Output is JSON by default. Use --text for human-readable format.

Usage:
    python live-score.py -n <namespace> -e <experiment_id> [--pre] [--api-key KEY]
    python live-score.py -e <experiment_id> [--pre] [--text]

Examples:
    python live-score.py -n Qwen-SWE-RL -e terminal-bench-2.0-20260623_001141 --pre
    python live-score.py -e my-experiment --api-key sk-xxx --text
"""

import argparse
import json
import math
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed


# ─── RC CLI helpers ──────────────────────────────────────────────────────────

def run_rc(cmd, timeout=60):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        return None, proc.stderr.strip()
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout), None
        except json.JSONDecodeError:
            # Return raw text for partial parsing
            return {"_raw": proc.stdout, "_truncated": True}, None
    return None, "empty response"


def build_base_cmd(namespace, experiment_id, env_flag):
    cmd = ["rc", "agent", "view", "-e", experiment_id]
    if namespace:
        cmd += ["-n", namespace]
    if env_flag:
        cmd.append(env_flag)
    return cmd


def fetch_experiment(namespace, experiment_id, env_flag, api_key):
    """Fetch all jobs from experiment with pagination."""
    all_jobs = []
    offset = 0
    limit = 100

    while True:
        cmd = build_base_cmd(namespace, experiment_id, env_flag)
        cmd += ["-o", "json", "--limit", str(limit), "--offset", str(offset)]
        if api_key:
            cmd += ["--api-key", api_key]
        data, err = run_rc(cmd, timeout=120)
        if err:
            print(f"Error: {err}", file=sys.stderr)
            sys.exit(1)
        if not data:
            break

        jobs = data.get("jobs", [])
        all_jobs.extend(jobs)

        pagination = data.get("pagination", {})
        total = pagination.get("total", len(jobs))
        if offset + limit >= total:
            break
        offset += limit

    if data:
        data["jobs"] = all_jobs
    else:
        data = {"jobs": all_jobs}
    return data


def fetch_job_detail(namespace, experiment_id, job_name, env_flag, api_key):
    cmd = build_base_cmd(namespace, experiment_id, env_flag)
    cmd += ["-j", job_name, "-o", "json"]
    if api_key:
        cmd += ["--api-key", api_key]
    try:
        data, _ = run_rc(cmd, timeout=90)
        return data or {}
    except Exception:
        return {}


# ─── Data extraction ─────────────────────────────────────────────────────────

def parse_truncated_json(raw):
    """Extract reward_stats and task_name from truncated JSON output."""
    rewards = []
    task_name = None

    # Extract task_name from tasks array
    task_match = re.search(r'"task_name":\s*"([^"]+)"', raw)
    if task_match:
        task_name = task_match.group(1)

    # Extract reward_stats — handles nested dict like {"reward": {"1.0": [...]}}
    reward_section = re.search(r'"reward_stats":\s*\{(.*?)\}\s*\}', raw, re.DOTALL)
    if reward_section:
        # Find all reward value -> trial list pairs
        for m in re.finditer(r'"([0-9.]+)":\s*\[([^\]]*)\]', reward_section.group(1)):
            reward_val = float(m.group(1))
            trial_list = m.group(2)
            n_trials = trial_list.count('"') // 2
            rewards.extend([reward_val] * n_trials)

    # Extract n_errors
    n_errors = 0
    err_match = re.search(r'"n_errors":\s*(\d+)', raw)
    if err_match:
        n_errors = int(err_match.group(1))

    # Extract avg_duration_ms
    dur_match = re.search(r'"avg_duration_ms":\s*([0-9.]+)', raw)
    duration_ms = float(dur_match.group(1)) if dur_match else None

    return task_name, rewards, n_errors, duration_ms


def extract_job_record(view_data, job_meta):
    """Build a job-level record from job detail response."""
    agent = job_meta.get("agents", ["unknown"])[0] if job_meta.get("agents") else "unknown"
    model = job_meta.get("models", ["unknown"])[0] if job_meta.get("models") else "unknown"
    dataset = job_meta.get("datasets", ["unknown"])[0] if job_meta.get("datasets") else "unknown"
    n_total_trials = job_meta.get("n_total_trials", 0)
    status = "done" if job_meta.get("finished_at") else "running"

    # Handle truncated JSON via regex parsing
    if view_data.get("_truncated"):
        task_name, rewards, n_errors, duration_ms = parse_truncated_json(view_data["_raw"])
        n_pass = sum(1 for r in rewards if r > 0)
        n_fail = sum(1 for r in rewards if r == 0)
        return {
            "job_name": job_meta.get("name", "unknown"),
            "task_name": task_name,
            "status": status,
            "agent": agent,
            "model": model,
            "dataset": dataset,
            "n_total_trials": n_total_trials,
            "n_completed": len(rewards),
            "n_errors": n_errors,
            "n_pass": n_pass,
            "n_fail": n_fail,
            "pass_rate": round(n_pass / len(rewards) * 100, 2) if rewards else None,
            "avg_reward": round(sum(rewards) / len(rewards), 4) if rewards else None,
            "avg_duration_s": round(duration_ms / 1000, 1) if duration_ms else None,
            "rewards": rewards,
        }

    # Normal full JSON parsing
    job = view_data.get("job", {})
    stats = job.get("stats", {})
    evals = stats.get("evals", {})
    tasks = view_data.get("tasks", [])

    task_name = tasks[0].get("task_name", "unknown") if tasks else "unknown"
    duration_ms = tasks[0].get("avg_duration_ms") if tasks else None

    # Collect per-trial rewards from reward_stats
    rewards = []
    for eval_data in evals.values():
        reward_map = eval_data.get("reward_stats", {}).get("reward", {})
        for reward_val, trial_names in reward_map.items():
            for _ in trial_names:
                rewards.append(float(reward_val))

    # Fallback: tasks[].avg_reward
    if not rewards and tasks:
        t = tasks[0]
        n_completed = t.get("n_completed", 0)
        avg_reward = t.get("avg_reward")
        if n_completed > 0 and avg_reward is not None:
            rewards = [float(avg_reward)] * n_completed

    # Errors count
    n_errors = stats.get("n_errors", 0)
    if not n_errors:
        for eval_data in evals.values():
            n_errors += eval_data.get("n_errors", 0)

    n_pass = sum(1 for r in rewards if r > 0)
    n_fail = sum(1 for r in rewards if r == 0)

    return {
        "job_name": job_meta.get("name", job.get("name", "unknown")),
        "task_name": task_name,
        "status": status,
        "agent": agent,
        "model": model,
        "dataset": dataset,
        "n_total_trials": n_total_trials,
        "n_completed": len(rewards),
        "n_errors": n_errors,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "pass_rate": round(n_pass / len(rewards) * 100, 2) if rewards else None,
        "avg_reward": round(sum(rewards) / len(rewards), 4) if rewards else None,
        "avg_duration_s": round(duration_ms / 1000, 1) if duration_ms else None,
        "rewards": rewards,
    }


def build_record_from_listing(job_meta):
    """Build a job record from listing data when detail fetch fails.

    Uses evals.metrics[0].mean as avg_reward and n_completed_trials for count.
    """
    agent = job_meta.get("agents", ["unknown"])[0] if job_meta.get("agents") else "unknown"
    model = job_meta.get("models", ["unknown"])[0] if job_meta.get("models") else "unknown"
    dataset = job_meta.get("datasets", ["unknown"])[0] if job_meta.get("datasets") else "unknown"
    n_completed = job_meta.get("n_completed_trials", 0)
    n_errors = job_meta.get("n_errors", 0)
    n_total_trials = job_meta.get("n_total_trials", 0)
    status = "done" if job_meta.get("finished_at") else "running"

    # Extract mean reward from listing evals
    avg_reward = None
    evals = job_meta.get("evals", {})
    for eval_data in evals.values():
        metrics = eval_data.get("metrics", [])
        if metrics and "mean" in metrics[0]:
            avg_reward = metrics[0]["mean"]
            break

    # Reconstruct rewards list from avg_reward * n_completed (approximate)
    rewards = []
    if n_completed > 0 and avg_reward is not None:
        rewards = [float(avg_reward)] * n_completed

    if rewards:
        n_pass = sum(1 for r in rewards if r > 0)
        n_fail = sum(1 for r in rewards if r == 0)
        pass_rate = round(n_pass / len(rewards) * 100, 2)
    else:
        n_pass = None
        n_fail = None
        pass_rate = None

    return {
        "job_name": job_meta.get("name", "unknown"),
        "task_name": None,
        "status": status,
        "agent": agent,
        "model": model,
        "dataset": dataset,
        "n_total_trials": n_total_trials,
        "n_completed": n_completed,
        "n_errors": n_errors,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "pass_rate": pass_rate,
        "avg_reward": float(avg_reward) if avg_reward is not None else None,
        "avg_duration_s": None,
        "rewards": rewards,
        "_source": "listing_fallback",
    }


def build_pending_record(job_meta):
    """Build a record for a job with no data at all."""
    agent = job_meta.get("agents", ["unknown"])[0] if job_meta.get("agents") else "unknown"
    model = job_meta.get("models", ["unknown"])[0] if job_meta.get("models") else "unknown"
    dataset = job_meta.get("datasets", ["unknown"])[0] if job_meta.get("datasets") else "unknown"

    return {
        "job_name": job_meta.get("name", "unknown"),
        "task_name": None,
        "status": "done" if job_meta.get("finished_at") else "running",
        "agent": agent,
        "model": model,
        "dataset": dataset,
        "n_total_trials": job_meta.get("n_total_trials", 0),
        "n_completed": 0,
        "n_errors": job_meta.get("n_errors", 0),
        "n_pass": None,
        "n_fail": None,
        "pass_rate": None,
        "avg_reward": None,
        "avg_duration_s": None,
        "rewards": [],
    }


# ─── Statistics ──────────────────────────────────────────────────────────────

def percentile(sorted_values, p):
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (n - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def compute_summary(job_records):
    """Compute summary from job-level records.

    pass_rate = fraction of scored jobs with avg_reward > 0.
    """
    scored_jobs = [j for j in job_records if j["avg_reward"] is not None]
    if not scored_jobs:
        return None

    n_jobs_pass = sum(1 for j in scored_jobs if j["avg_reward"] > 0)
    all_rewards = []
    for j in scored_jobs:
        all_rewards.extend(j["rewards"])

    sorted_rewards = sorted(all_rewards)
    n = len(sorted_rewards)
    mean = sum(sorted_rewards) / n if n else 0
    variance = sum((r - mean) ** 2 for r in sorted_rewards) / n if n > 1 else 0.0

    return {
        "pass_rate": round(n_jobs_pass / len(scored_jobs) * 100, 2),
        "n_jobs_scored": len(scored_jobs),
        "n_jobs_pass": n_jobs_pass,
        "n_jobs_fail": len(scored_jobs) - n_jobs_pass,
        "trial_pass_rate": round(sum(1 for r in all_rewards if r > 0) / n * 100, 2) if n else 0,
        "total_trials_scored": n,
        "mean_reward": round(mean, 4),
        "median_reward": round(percentile(sorted_rewards, 0.5), 4),
        "std_reward": round(math.sqrt(variance), 4),
        "p25_reward": round(percentile(sorted_rewards, 0.25), 4),
        "p75_reward": round(percentile(sorted_rewards, 0.75), 4),
        "min_reward": sorted_rewards[0] if sorted_rewards else None,
        "max_reward": sorted_rewards[-1] if sorted_rewards else None,
    }


# ─── Text output ─────────────────────────────────────────────────────────────

def print_text_report(progress, summary, job_records):
    print("=" * 64)
    print("  ROCK Experiment Live Score")
    print("=" * 64)
    print()

    p = progress
    pct = (p["completed_trials"] + p["total_errors"]) / p["total_trials"] * 100 if p["total_trials"] else 0
    print(f"  Progress:    {p['completed_trials'] + p['total_errors']}/{p['total_trials']} trials ({pct:.1f}%)")
    print(f"  Jobs:        {p['jobs_total']} total | {p['jobs_done']} done | {p['jobs_total'] - p['jobs_done']} running")
    print()

    if not summary:
        print("  No scored jobs yet.")
        print("=" * 64)
        return

    print("─── Summary ────────────────────────────────────────────────────")
    print()
    print(f"  Pass Rate (job):   {summary['pass_rate']:.1f}%  ({summary['n_jobs_pass']}/{summary['n_jobs_scored']} jobs)")
    print(f"  Pass Rate (trial): {summary['trial_pass_rate']:.1f}%  ({summary['total_trials_scored']} trials)")
    print(f"  Mean Reward:       {summary['mean_reward']:.4f}")
    print(f"  Median Reward:     {summary['median_reward']:.4f}")
    print(f"  Std:               {summary['std_reward']:.4f}")
    print()

    print("─── Jobs ───────────────────────────────────────────────────────")
    print()
    header = f"  {'Task':<35} {'Status':<8} {'Pass%':>6} {'Trials':>8} {'AvgR':>6}"
    print(header)
    print(f"  {'─' * 35} {'─' * 8} {'─' * 6} {'─' * 8} {'─' * 6}")

    sorted_jobs = sorted(job_records, key=lambda x: (x["avg_reward"] if x["avg_reward"] is not None else -1, x["job_name"]))
    for j in sorted_jobs:
        name = (j["task_name"] or j["job_name"])[:35]
        status = j["status"]
        if j["pass_rate"] is not None:
            pass_str = f"{j['pass_rate']:>5.1f}%"
            avg_r = f"{j['avg_reward']:.2f}"
        else:
            pass_str = "   N/A"
            avg_r = "  N/A"
        trials = f"{j['n_completed']}/{j['n_total_trials']}"
        print(f"  {name:<35} {status:<8} {pass_str} {trials:>8} {avg_r:>6}")
    print()
    print("=" * 64)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Live scoring for ROCK experiments")
    parser.add_argument("-n", "--namespace", help="Agent namespace")
    parser.add_argument("-e", "--experiment", required=True, help="Experiment ID")
    parser.add_argument("--pre", action="store_true", help="Use pre-production environment")
    parser.add_argument("--api-key", help="API key for rc commands")
    parser.add_argument("--text", action="store_true", help="Output as human-readable text instead of JSON")
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers for fetching job details")
    args = parser.parse_args()

    env_flag = "--pre" if args.pre else None

    # Step 1: fetch experiment listing
    print(f"Fetching experiment {args.experiment}...", file=sys.stderr)
    exp_data = fetch_experiment(args.namespace, args.experiment, env_flag, args.api_key)
    if not exp_data:
        print("Empty response.", file=sys.stderr)
        sys.exit(1)
    jobs = exp_data.get("jobs", [])
    if not jobs:
        print("No jobs found.", file=sys.stderr)
        sys.exit(1)


    # Step 2: fetch details for all jobs in parallel
    print(f"Fetching {len(jobs)} job details...", file=sys.stderr)

    job_records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                fetch_job_detail, args.namespace, args.experiment,
                j["name"], env_flag, args.api_key
            ): j
            for j in jobs
        }
        for future in as_completed(futures):
            job_meta = futures[future]
            view_data = future.result()
            if view_data and view_data.get("_truncated"):
                # Truncated JSON — parse via regex
                record = extract_job_record(view_data, job_meta)
                job_records.append(record)
            elif view_data and (view_data.get("tasks") or view_data.get("job", {}).get("stats", {}).get("evals")):
                record = extract_job_record(view_data, job_meta)
                job_records.append(record)
            elif job_meta.get("n_completed_trials", 0) > 0:
                # Detail fetch failed but listing shows completed trials — use listing data
                record = build_record_from_listing(job_meta)
                job_records.append(record)
            else:
                job_records.append(build_pending_record(job_meta))

    # Step 3: compute summary
    summary = compute_summary(job_records)

    # Step 4: build progress
    progress = {
        "completed_trials": sum(j.get("n_completed_trials", 0) for j in jobs),
        "total_trials": sum(j.get("n_total_trials", 0) for j in jobs),
        "total_errors": sum(j.get("n_errors", 0) for j in jobs),
        "jobs_total": len(jobs),
        "jobs_done": sum(1 for j in jobs if j.get("finished_at")),
    }

    # Step 5: output
    if args.text:
        print_text_report(progress, summary, job_records)
    else:
        output = {
            "experiment": args.experiment,
            "namespace": args.namespace,
            "progress": progress,
            "summary": summary,
            "jobs": sorted(job_records, key=lambda x: x["job_name"]),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
