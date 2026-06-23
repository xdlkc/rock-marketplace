#!/usr/bin/env python3
"""
fetch-overview.py — 通过 live-score.py 获取 bench 实验概览，识别需要深度分析的 job

背景：
    rc agent view -e <EXP> -o json 对大型 job 会出现 JSON 截断问题（约 50/89 job），
    rc agent view --limit 200 会触发 422 错误（API 上限 100 条/页）。
    因此本脚本改用 live-score.py 作为数据源，该工具已内置截断处理和分页逻辑。

用法:
    python3 fetch-overview.py <EXP_ID> [--pre] [--output FILE] [--live-score-path PATH]

输出:
    - 控制台：人类可读的实验摘要
    - 文件（--output 指定时）：结构化 JSON，供下游分析脚本消费

数据源:
    优先使用 live-score.py JSON 输出；若失败则尝试解析 --text 输出作为降级方案。
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any


# ──────────────────────────── live-score.py 发现 ────────────────────────────

LIVE_SCORE_SEARCH_PATHS = [
    # 常见安装路径（按优先级排列）
    os.path.expanduser("~/.claude/plugins/rock/skills/rock-eval/scripts/live-score.py"),
    os.path.expanduser("~/.claude/plugins/rock-eval/scripts/live-score.py"),
]


def find_live_score(explicit_path: str | None = None) -> str | None:
    """查找 live-score.py，返回绝对路径；找不到时返回 None。"""
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        print(f"错误：指定的 live-score-path 不存在：{explicit_path}", file=sys.stderr)
        return None

    # 先尝试已知路径
    for p in LIVE_SCORE_SEARCH_PATHS:
        if os.path.isfile(p):
            return p

    # 动态搜索（较慢，作为兜底）
    try:
        result = subprocess.run(
            ["find", os.path.expanduser("~/.claude/plugins"),
             "-path", "*/rock-eval/scripts/live-score.py"],
            capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line and os.path.isfile(line):
                return line
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


# ──────────────────────────── 运行 live-score.py ────────────────────────────

def run_live_score_json(live_score_path: str, exp_id: str, pre: bool) -> dict[str, Any] | None:
    """
    运行 live-score.py 并获取 JSON 输出（不加 --text）。
    返回解析后的 dict；失败时返回 None。
    """
    cmd = [sys.executable, live_score_path, "-e", exp_id]
    if pre:
        cmd.append("--pre")
    # 不加 --text，获取 JSON 输出

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        print("错误：live-score.py 执行超时（300s）。", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"错误：无法执行 {sys.executable}，请检查 Python 环境。", file=sys.stderr)
        return None

    if result.returncode != 0:
        print(f"警告：live-score.py 返回非零退出码（{result.returncode}）。", file=sys.stderr)
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()[:300]}", file=sys.stderr)

    stdout = result.stdout.strip()
    if not stdout:
        print("错误：live-score.py 返回空输出。", file=sys.stderr)
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"警告：无法解析 live-score.py 的 JSON 输出: {e}", file=sys.stderr)
        print(f"  原始输出（前 500 字符）：{stdout[:500]}", file=sys.stderr)
        return None


def run_live_score_text(live_score_path: str, exp_id: str, pre: bool) -> str | None:
    """
    运行 live-score.py --text，返回文本输出。
    作为 JSON 解析失败时的降级方案。
    """
    cmd = [sys.executable, live_score_path, "-e", exp_id, "--text"]
    if pre:
        cmd.append("--pre")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        print("错误：live-score.py --text 执行超时（300s）。", file=sys.stderr)
        return None

    if result.returncode != 0 and not result.stdout.strip():
        return None
    return result.stdout.strip() or None


# ──────────────────────────── 解析 live-score.py 输出 ────────────────────────────

def parse_live_score_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从 live-score.py JSON 输出中提取 job 摘要列表。

    live-score.py JSON 结构：
    {
        "experiment": "...",
        "namespace": "...",
        "progress": {
            "completed_trials": N,
            "total_trials": N,
            "total_errors": N,
            "jobs_total": N,
            "jobs_done": N,
        },
        "summary": {
            "score": 0.6884,
            "pass_rate": 77.8,
            ...
        },
        "jobs": [
            {
                "job_name": "...",
                "task_name": "...",
                "status": "done" | "running",
                "n_total_trials": 5,
                "n_completed": 5,
                "n_errors": 1,
                "avg_reward": 0.80,
                "pass_rate": 80.0,
                ...
            }
        ]
    }
    """
    jobs = data.get("jobs", [])
    summaries = []
    for j in jobs:
        task_name = j.get("task_name") or j.get("job_name", "unknown")
        avg_reward = j.get("avg_reward")
        n_completed = j.get("n_completed", 0)
        status = j.get("status", "unknown")

        needs = _needs_deep_analysis(avg_reward, j.get("n_errors", 0), n_completed, status)

        summaries.append({
            "job_name": j.get("job_name", "unknown"),
            "task_name": task_name,
            "avg_reward": avg_reward,
            "n_total_trials": j.get("n_total_trials", 0),
            "n_completed_trials": n_completed,
            "n_errors": j.get("n_errors", 0),
            "pass_rate": j.get("pass_rate"),
            "avg_duration_s": j.get("avg_duration_s"),
            "agent_name": j.get("agent", ""),
            "model_name": j.get("model", ""),
            "status": status,
            "needs_analysis": needs,
        })
    return summaries


def parse_live_score_text(text: str) -> list[dict[str, Any]]:
    """
    从 live-score.py --text 输出中解析 job 列表（降级方案）。

    文本格式示例（Jobs 表格部分）：
      Task                                Status   Pass%   Trials   AvgR
      ─────────────────────────────────── ──────── ────── ──────── ──────
      some-task-name                      done     80.0%      4/5   0.80
      other-task                          running    N/A      0/5    N/A
    """
    summaries = []
    in_jobs_section = False
    in_table = False

    for line in text.splitlines():
        stripped = line.strip()

        if "─── Jobs" in stripped or stripped.startswith("─── Jobs"):
            in_jobs_section = True
            in_table = False
            continue

        if in_jobs_section:
            # 跳过表头行
            if "Task" in stripped and "Status" in stripped and "Pass%" in stripped:
                in_table = True
                continue
            # 跳过分隔线
            if stripped.startswith("─") or stripped.startswith("="):
                if in_table:
                    # 结尾分隔线，退出 jobs 段
                    break
                continue

            if in_table and stripped:
                # 解析数据行
                parts = stripped.split()
                if len(parts) < 4:
                    continue

                # task_name 可能包含空格，status 是 done/running，
                # 采用从右侧解析已知格式字段的方式
                try:
                    avg_r_str = parts[-1]
                    trials_str = parts[-2]    # 格式 "N/M"
                    pass_str = parts[-3]      # 格式 "XX.X%" 或 "N/A"
                    status = parts[-4]

                    task_name = " ".join(parts[:-4]).strip()
                    if not task_name:
                        continue

                    avg_reward = None if avg_r_str in ("N/A", "N/A") else float(avg_r_str)
                    n_completed, n_total = 0, 0
                    if "/" in trials_str:
                        n_completed, n_total = (int(x) for x in trials_str.split("/"))

                    needs = _needs_deep_analysis(avg_reward, 0, n_completed, status)

                    summaries.append({
                        "job_name": task_name,
                        "task_name": task_name,
                        "avg_reward": avg_reward,
                        "n_total_trials": n_total,
                        "n_completed_trials": n_completed,
                        "n_errors": 0,  # text 输出不含 n_errors
                        "pass_rate": None if pass_str == "N/A" else float(pass_str.rstrip("%")),
                        "avg_duration_s": None,
                        "agent_name": "",
                        "model_name": "",
                        "status": status,
                        "needs_analysis": needs,
                    })
                except (ValueError, IndexError):
                    continue

    return summaries


# ──────────────────────────── 判断是否需要深度分析 ────────────────────────────

def _needs_deep_analysis(
    avg_reward: float | None,
    n_errors: int,
    n_completed: int,
    status: str,
) -> bool:
    """
    判断该 job 是否需要深度 trajectory 分析。

    跳过条件：仍在运行且 0 trials 完成（infra 问题或等待调度）。
    """
    # 仍在运行且没有任何完成的 trial：跳过（无数据可分析）
    if status == "running" and n_completed == 0:
        return False
    # 有错误
    if n_errors and n_errors > 0:
        return True
    # reward 不满分
    if avg_reward is not None and avg_reward < 1.0:
        return True
    # 有 completed trials 但 reward 未知：保守纳入
    if avg_reward is None and n_completed > 0:
        return True
    return False


# ──────────────────────────── 分数计算 ────────────────────────────

def compute_score(job_summaries: list[dict]) -> float | None:
    """Score = per-task avg_reward 的均值（与 live-score.py 一致）。"""
    rewards = [j["avg_reward"] for j in job_summaries if j.get("avg_reward") is not None]
    if not rewards:
        return None
    return sum(rewards) / len(rewards)


# ──────────────────────────── 打印摘要 ────────────────────────────

def print_summary(
    exp_id: str,
    pre: bool,
    job_summaries: list[dict],
    score: float | None,
) -> None:
    total = len(job_summaries)
    passed = sum(
        1 for j in job_summaries
        if j.get("avg_reward") is not None and j["avg_reward"] >= 1.0
    )
    needs = [j for j in job_summaries if j.get("needs_analysis")]
    skipped = [j for j in job_summaries if not j.get("needs_analysis") and j.get("avg_reward") is None]

    env_label = "staging (--pre)" if pre else "prod"
    score_str = f"{score:.4f}" if score is not None else "N/A"

    print("=" * 62)
    print(f"实验 ID  : {exp_id}")
    print(f"环境     : {env_label}")
    print(f"总任务数  : {total}")
    print(f"通过(1.0): {passed}")
    print(f"需分析数  : {len(needs)}")
    if skipped:
        print(f"无数据跳过: {len(skipped)}（仍在运行 / 0 trials 完成）")
    print(f"Score    : {score_str}")
    print("=" * 62)

    if needs:
        print("\n需要深度分析的 job：")
        print(f"  {'任务名':<42} {'Reward':>8}  {'Trials':>8}  {'Status':<8}")
        print("  " + "-" * 76)
        for j in sorted(needs, key=lambda x: (x.get("avg_reward") or 0)):
            reward_str = f"{j['avg_reward']:.3f}" if j.get("avg_reward") is not None else "  N/A"
            trials = f"{j['n_completed_trials']}/{j['n_total_trials']}"
            print(
                f"  {j['task_name']:<42} {reward_str:>8}  {trials:>8}  {j.get('status', '?'):<8}"
            )

    if skipped:
        print(f"\n跳过（无数据）的 job（{len(skipped)} 个）：")
        print(f"  {', '.join(j['task_name'] for j in skipped)}")

    success_jobs = [j for j in job_summaries if not j.get("needs_analysis") and j.get("avg_reward") is not None]
    if success_jobs:
        print(f"\n成功任务（reward=1.0，不做深度分析，共 {len(success_jobs)} 个）：")
        names = ", ".join(j["task_name"] for j in success_jobs)
        if len(names) > 120:
            lines = []
            line = ""
            for name in [j["task_name"] for j in success_jobs]:
                if len(line) + len(name) + 2 > 110:
                    lines.append(line.rstrip(", "))
                    line = ""
                line += name + ", "
            if line:
                lines.append(line.rstrip(", "))
            names = "\n  ".join(lines)
        print(f"  {names}")


# ──────────────────────────── JSON 输出构建 ────────────────────────────

def build_output(
    exp_id: str,
    pre: bool,
    job_summaries: list[dict],
    score: float | None,
) -> dict[str, Any]:
    needs = [j for j in job_summaries if j.get("needs_analysis")]
    skipped = [j for j in job_summaries if not j.get("needs_analysis") and j.get("avg_reward") is None]
    return {
        "experiment_id": exp_id,
        "environment": "staging" if pre else "prod",
        "total_jobs": len(job_summaries),
        "passed": sum(
            1 for j in job_summaries
            if j.get("avg_reward") is not None and j["avg_reward"] >= 1.0
        ),
        "failed": len(needs),
        "skipped_no_data": len(skipped),
        "score": score,
        "all_jobs": job_summaries,
        "jobs_to_analyze": needs,
    }


# ──────────────────────────── main ────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="通过 live-score.py 获取 bench 实验概览，识别需要深度分析的 job",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
说明:
    本脚本依赖 live-score.py（位于 rock-eval skill 的 scripts/ 目录）获取实验数据。
    避免直接调用 `rc agent view -o json`，因为该命令对大型 job 存在 JSON 截断问题，
    且 --limit 200 会触发 422 错误（API 上限 100 条/页）。

示例:
  python3 fetch-overview.py exp-abc123
  python3 fetch-overview.py exp-abc123 --pre
  python3 fetch-overview.py exp-abc123 --pre --output /tmp/bench/overview.json
  python3 fetch-overview.py exp-abc123 --pre --live-score-path /path/to/live-score.py
        """,
    )
    parser.add_argument("exp_id", help="实验 ID")
    parser.add_argument(
        "--pre",
        action="store_true",
        help="使用 staging 环境（预发），否则使用 prod",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="将结构化 JSON 写入指定文件（同时仍会打印到控制台）",
    )
    parser.add_argument(
        "--live-score-path",
        metavar="PATH",
        help="显式指定 live-score.py 路径（自动发现失败时使用）",
    )
    args = parser.parse_args()

    # ── 定位 live-score.py ──
    live_score_path = find_live_score(args.live_score_path)
    if not live_score_path:
        print(
            "错误：找不到 live-score.py。\n"
            "  请通过 --live-score-path 显式指定路径，或确保 rock-eval skill 已安装。\n"
            "  手动查找命令：find ~/.claude/plugins -path '*/rock-eval/scripts/live-score.py' 2>/dev/null",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"使用 live-score.py：{live_score_path}", file=sys.stderr)
    print(f"正在获取实验 {args.exp_id} 的数据...", file=sys.stderr)

    # ── 运行 live-score.py（JSON 模式）──
    live_data = run_live_score_json(live_score_path, args.exp_id, args.pre)

    job_summaries: list[dict[str, Any]]

    if live_data is not None and live_data.get("jobs"):
        # 从 JSON 输出解析
        job_summaries = parse_live_score_json(live_data)
        print(f"  已从 JSON 输出解析 {len(job_summaries)} 个 job。", file=sys.stderr)
    else:
        # 降级：尝试 --text 输出
        print("  JSON 解析失败，尝试 --text 输出作为降级方案...", file=sys.stderr)
        text_output = run_live_score_text(live_score_path, args.exp_id, args.pre)
        if not text_output:
            print("错误：live-score.py 输出解析完全失败。请检查实验 ID 和环境。", file=sys.stderr)
            sys.exit(1)
        job_summaries = parse_live_score_text(text_output)
        print(f"  已从文本输出解析 {len(job_summaries)} 个 job（降级模式，部分字段可能缺失）。", file=sys.stderr)

    if not job_summaries:
        print("警告：未找到任何 job。请检查实验 ID 和环境。", file=sys.stderr)

    score = compute_score(job_summaries)
    print_summary(args.exp_id, args.pre, job_summaries, score)

    if args.output:
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        output_data = build_output(args.exp_id, args.pre, job_summaries, score)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n结构化 JSON 已写入：{args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
