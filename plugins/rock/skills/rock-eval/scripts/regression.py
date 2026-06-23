#!/usr/bin/env python3
"""通用全量回归脚本 — 基于 rockcli 实现任意 template + 数据集的全量回归

子命令:
    run       执行回归任务
    report    查看结果报告
    sync      从服务端同步最新状态
    diagnose  失败排查
    retry     重跑失败任务

用法:
    python3 regression.py run --bench aone-bench --dataset alibaba/aone-bench-java100 \\
        --split delivery_0609-cn --agent claude-code --concurrency 20 --window-size 0

    python3 regression.py report [experiment_id]
    python3 regression.py sync [experiment_id]
    python3 regression.py diagnose [experiment_id]
    python3 regression.py diagnose [experiment_id] --task codereview-12345 --remote
    python3 regression.py retry [experiment_id] --bench aone-bench --agent claude-code \\
        --concurrency 10 --window-size 0
"""

import argparse
import fcntl
import json
import math
import os
import re
import time
import subprocess
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

# ─── 全局状态 ───

json_lock = threading.Lock()
dispatched_count = 0
count_lock = threading.Lock()

# 派发新鲜度阈值（秒）：dispatched_at 距当前时间小于该值的任务，
# 即便 job_name 尚未写回 JSON 也视作"正在派发中"，sync 不判 error，
# 避免巡检在 rc 子进程写回 job_name 前的窗口期误判把正在跑的任务判死。
DISPATCH_FRESHNESS_SECONDS = 300

LINE = "=" * 70

_UNSET = object()  # 占位符：表示 CLI 未显式传入该参数


class _AppendUnsetAction(argparse.Action):
    """append 兼容 _UNSET：flag 未出现时保留 _UNSET；首次出现时从 [] 起步再累加。

    argparse 原生 append action 会直接对 default 对象调 .append()，
    当 default=_UNSET 时会崩。此处手动把 _UNSET 视作「未初始化」。
    """

    def __call__(self, _parser, namespace, values, _option_string=None):  # argparse Action 固定签名
        items = getattr(namespace, self.dest, _UNSET)
        if items is _UNSET:
            items = []
        else:
            # 走到此处 items 必为已有的列表；复制一份避免污染 default
            items = list(items)  # type: ignore[arg-type]
        items.append(values)
        setattr(namespace, self.dest, items)


# 可保存字段清单（顺序即 JSON 字段顺序，便于人读；不含 experiment_id）
SAVE_FIELDS = [
    "bench", "dataset", "split", "agent",
    "image", "cluster", "model", "api_key",
    "ee", "set", "pre", "namespace", "cpus", "memory",
    "companion", "config", "async_mode", "user_id", "base_url",
    "auto_clear",
    "concurrency", "window_size", "tasks",
    "poll_interval", "poll_timeout",
]


# ─── 工具函数 ───

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path, data):
    """原子写入 JSON：写到同目录临时文件再 os.replace 覆盖，避免读到半截 JSON。

    os.replace 在同一文件系统上是原子的；临时文件用目标文件同目录、
    同后缀加 .tmp，保证与目标在同一个文件系统上。
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextmanager
def _file_lock(path):
    """跨进程文件锁（fcntl.flock 排他锁），保护 results JSON 的读-改-写。

    锁文件与目标 JSON 同目录、同后缀加 .lock。仅 Unix（darwin/linux）可用。
    锁层级约定：外层 json_lock（进程内线程安全），内层 _file_lock（跨进程），
    二者正交，调用方按此顺序嵌套即可。
    """
    path = Path(path)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "w") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)


def _is_dispatch_fresh(task, now=None, freshness=DISPATCH_FRESHNESS_SECONDS):
    """判断任务是否处于"刚派发"的新鲜窗口期内（dispatched_at < freshness 秒）。

    取舍：dispatched_at 为空/缺失/格式异常时返回 False（视作"不新鲜"），
    即仍可能被 sync 判 error。这样可避免异常数据导致任务被无限挂起、永远不被判错。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    dispatched_at = task.get("dispatched_at")
    if not dispatched_at:
        return False
    try:
        ts = datetime.fromisoformat(dispatched_at)
    except (ValueError, TypeError):
        return False
    # 兼容 naive datetime（无时区信息）:当作 UTC 处理
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() < freshness


def resolve_experiment(args):
    """根据位置参数或最新文件定位结果 JSON，返回 (path, data)"""
    exp = getattr(args, "experiment", None)
    if exp:
        if Path(exp).is_file():
            path = exp
        else:
            path = f"./results/{exp}.json"
            if not Path(path).exists():
                candidates = sorted(glob(f"./results/{exp}*.json"), reverse=True)
                if candidates:
                    path = candidates[0]
        if not Path(path).exists():
            print(f"错误: 找不到结果文件 {path}", file=sys.stderr)
            sys.exit(1)
    else:
        json_files = sorted(glob("./results/*.json"), key=lambda f: Path(f).stat().st_mtime, reverse=True)
        if not json_files:
            print("错误: results/ 下没有结果文件", file=sys.stderr)
            sys.exit(1)
        path = json_files[0]
    with open(path) as f:
        data = json.load(f)
    return path, data


def percentile(sorted_vals, p):
    """纯 Python 分位数，sorted_vals 已排序"""
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def format_duration(ms):
    """毫秒转人类可读"""
    if ms is None:
        return "-"
    s = ms / 1000
    if s < 60:
        return f"{s:.1f}s"
    m = int(s // 60)
    sec = s % 60
    if m < 60:
        return f"{m}m {sec:.0f}s"
    h = m // 60
    m = m % 60
    return f"{h}h {m}m"


def make_bar(value, max_value, width=30):
    """ASCII 进度条"""
    if max_value <= 0:
        return ""
    filled = int(value / max_value * width)
    return "█" * filled


def normalize_exception_msg(msg):
    """去除变量部分用于分组"""
    if not msg:
        return "(无异常信息)"
    msg = re.sub(r"codereview-\d+", "codereview-*", msg)
    msg = re.sub(r"swe-\d+", "swe-*", msg)
    msg = re.sub(r"[a-f0-9]{24,}", "*HASH*", msg)
    msg = re.sub(r"job-[a-f0-9]+", "job-*", msg)
    msg = re.sub(r"\d{14}", "*TS*", msg)
    msg = re.sub(r"prewarm-\d+", "prewarm-*", msg)
    msg = re.sub(r"codereview-\*-[a-z0-9]{5,10}", "codereview-*-*RND*", msg)
    msg = re.sub(r"swe-\*-[a-z0-9]{5,10}", "swe-*-*RND*", msg)
    return msg[:200]


# ─── 结果文件管理 ───

def init_result_json(result_json, experiment_id, config, all_tasks, extra_fields=None):
    if Path(result_json).exists():
        return
    data = {
        "experiment_id": experiment_id,
        "bench": config.bench,
        "dataset": getattr(config, "dataset", ""),
        "split": config.split,
        "agent": config.agent,
        "image": getattr(config, "image", "") or "",
        "cluster": getattr(config, "cluster", "") or "",
        "model": getattr(config, "model", "") or "",
        "concurrency": config.concurrency,
        "window_size": config.window_size,
        "started_at": now_iso(),
        "finished_at": None,
        "summary": {
            "total": len(all_tasks),
            "dispatched": 0,
            "success": 0,
            "error": 0,
            "pending": len(all_tasks),
        },
        "tasks": {},
    }
    if extra_fields:
        data.update(extra_fields)
    Path(result_json).parent.mkdir(parents=True, exist_ok=True)
    # 首次创建通常无并发,但为与其他写点保持一致仍加文件锁,并原子写。
    with _file_lock(result_json):
        _atomic_write_json(result_json, data)


def update_task_result(result_json, task_id, total_tasks, status, sandbox_id="", job_name="", extra=None):
    # 锁层级:外层 json_lock(进程内线程安全) + 内层 _file_lock(跨进程排他)。
    # 读-改-写整段都在跨进程锁内,写回走原子写,杜绝并发读半截 JSON / 互相覆盖。
    with json_lock, _file_lock(result_json):
        with open(result_json) as f:
            data = json.load(f)

        now = now_iso()
        if task_id not in data["tasks"]:
            data["tasks"][task_id] = {
                "task_id": task_id,
                "status": "pending",
                "sandbox_id": None,
                "job_name": None,
                "dispatched_at": None,
                "finished_at": None,
                "reward": None,
                "n_trials": 0,
                "n_completed": 0,
                "n_errors": 0,
                "exception_type": None,
                "exception_message": None,
                "agent_name": None,
                "duration_ms": None,
            }

        task = data["tasks"][task_id]
        task["status"] = status
        if sandbox_id:
            task["sandbox_id"] = sandbox_id
        if job_name:
            task["job_name"] = job_name
        if status == "dispatched":
            task["dispatched_at"] = now
        if status in ("success", "error"):
            task["finished_at"] = now
        if extra:
            for k, v in extra.items():
                task[k] = v

        summary = {"total": total_tasks, "dispatched": 0, "success": 0, "error": 0, "pending": 0}
        for t in data["tasks"].values():
            s = t.get("status", "pending")
            if s == "dispatched":
                summary["dispatched"] += 1
            elif s == "success":
                summary["success"] += 1
            elif s == "error":
                summary["error"] += 1
        summary["pending"] = total_tasks - summary["dispatched"] - summary["success"] - summary["error"]
        data["summary"] = summary

        _atomic_write_json(result_json, data)


# ─── RC CLI 交互 ───

def _fetch_view_data(experiment_id, job_name, api_key):
    try:
        cmd = ["rc", "agent", "view", "-e", experiment_id, "-j", job_name, "--pre", "-o", "json"]
        if api_key:
            cmd += ["--api-key", api_key]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    except Exception:
        return {}


def _fetch_experiment_jobs(experiment_id, api_key):
    """Fetch all job names from the remote experiment."""
    try:
        cmd = ["rc", "agent", "view", "-e", experiment_id, "--pre", "--limit", "1000", "-o", "json"]
        if api_key:
            cmd += ["--api-key", api_key]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.stdout.strip():
            data = json.loads(proc.stdout)
            return data.get("jobs", [])
    except Exception:
        pass
    return []


def _discover_task_job_mapping(experiment_id, api_key, job_names, concurrency=10):
    """Query each job to get its task_name, returning {task_name: job_name} mapping."""
    mapping = {}

    def query_one(job_name):
        view_data = _fetch_view_data(experiment_id, job_name, api_key)
        tasks = view_data.get("tasks", [])
        if tasks:
            return tasks[0].get("task_name"), job_name, view_data
        return None, job_name, view_data

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(query_one, jn): jn for jn in job_names}
        for future in as_completed(futures):
            try:
                task_name, job_name, view_data = future.result()
                if task_name:
                    if task_name not in mapping:
                        mapping[task_name] = (job_name, view_data)
                    else:
                        # Keep the newer job (later started_at or finished_at)
                        existing_finished = mapping[task_name][1].get("finished_at") or ""
                        new_finished = view_data.get("finished_at") or ""
                        if new_finished > existing_finished:
                            mapping[task_name] = (job_name, view_data)
            except Exception:
                pass
    return mapping


def parse_job_from_log(experiment_id, task_id):
    """从日志文件 ./logs/<experiment_id>/<task_id>.log 提取 job_name 和 sandbox_id。

    用于 regression.py 中途重启后，从日志回填结果文件中缺失的 job_name，
    提取不到时返回 (None, None)。
    """
    log_path = Path(f"./logs/{experiment_id}/{task_id}.log")
    if not log_path.exists():
        return None, None
    try:
        content = log_path.read_text(encoding="utf-8")
    except Exception:
        return None, None
    job_match = re.search(r"job_name=([a-zA-Z0-9_-]+)", content)
    sandbox_match = re.search(r"sandbox_id=([a-f0-9]+)", content)
    job_name = job_match.group(1) if job_match else None
    sandbox_id = sandbox_match.group(1) if sandbox_match else None
    return job_name, sandbox_id


def query_and_update_task(result_json, experiment_id, task_id, total_tasks, job_name, sandbox_id, api_key, poll_interval, poll_timeout):
    view_data = {}
    waited = 0
    while waited < poll_timeout:
        view_data = _fetch_view_data(experiment_id, job_name, api_key)
        tasks = view_data.get("tasks", [])
        if tasks and tasks[0].get("n_completed", 0) + tasks[0].get("n_errors", 0) > 0:
            break
        time.sleep(poll_interval)
        waited += poll_interval

    extra = extract_task_extra(view_data)
    status = "error" if extra.get("n_errors", 0) > 0 else "success"
    update_task_result(result_json, task_id, total_tasks, status, sandbox_id, job_name, extra)


def extract_task_extra(view_data):
    """从 rc agent view 的 JSON 响应中提取任务结果字段"""
    extra = {}
    tasks = view_data.get("tasks", [])
    if tasks:
        t = tasks[0]
        extra["n_trials"] = t.get("n_trials", 0)
        extra["n_completed"] = t.get("n_completed", 0)
        extra["n_errors"] = t.get("n_errors", 0)
        extra["agent_name"] = t.get("agent_name")
        extra["reward"] = t.get("avg_reward")
        dur = t.get("avg_duration_ms")
        extra["duration_ms"] = round(dur) if dur else None

    # job-level finished_at indicates the job is done regardless of task aggregation
    extra["finished_at"] = view_data.get("finished_at")

    trial_detail = view_data.get("trialDetail", {})
    trial = trial_detail.get("trial", {})

    exc = trial.get("exception_info") or {}
    if exc:
        extra["exception_type"] = exc.get("exception_type")
        extra["exception_message"] = exc.get("exception_message")

    # Fallback: when n_completed/n_errors are both 0 (platform aggregation delay)
    # but trialDetail has actual results, extract from there
    if extra.get("n_completed", 0) + extra.get("n_errors", 0) == 0:
        reward_map = trial_detail.get("reward") or view_data.get("reward")
        if isinstance(reward_map, dict):
            for reward_val, trial_names in reward_map.items():
                if trial_names:
                    extra["reward"] = float(reward_val)
                    extra["n_completed"] = 1
                    break
        if exc:
            extra["n_errors"] = 1
            extra["n_completed"] = 1

    return extra


# ─── run 子命令 ───

def fetch_task_list(dataset, split, api_key):
    print(f"正在获取任务列表: dataset={dataset} split={split} ...")
    cmd = ["rc", "datasets", dataset, "tasks", "--split", split, "--pre", "--limit", "10000"]
    if api_key:
        cmd += ["--api-key", api_key]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        print(f"错误: 获取任务列表失败\n{proc.stderr}", file=sys.stderr)
        sys.exit(1)

    tasks = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if re.match(r"^[a-zA-Z][\w.-]+$", line) and not line.startswith(("#", "=", "-")):
            tasks.append(line)
    if not tasks:
        print(f"错误: 未从 dataset={dataset} split={split} 获取到任何任务", file=sys.stderr)
        sys.exit(1)

    print(f"获取到 {len(tasks)} 个任务")
    return tasks


def save_config(args, path):
    """把 SAVE_FIELDS 中各字段序列化为 JSON 写到 path（先建父目录）。"""
    data = {f: getattr(args, f) for f in SAVE_FIELDS}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"配置已保存: {path}")


def load_config(path):
    """读取 JSON 配置文件，返回 dict。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def apply_config(args, config_path):
    """--from-config：用 JSON 填充 CLI 未显式传入的字段，CLI 显式值覆盖 JSON。"""
    cfg = load_config(config_path)
    for f in SAVE_FIELDS:
        if f not in cfg:
            continue
        cur = getattr(args, f, _UNSET)
        # CLI 未传（_UNSET）才用 JSON 的值；CLI 传了则保留（覆盖 JSON）
        if cur is _UNSET:
            setattr(args, f, cfg[f])
    print(f"已加载配置: {config_path}")


def normalize_args(args):
    """把所有仍为 _UNSET 的可保存字段还原成真实默认值；必传字段缺失则报错退出。

    对 report/sync/diagnose 无害：这些子命令的 args 没有可保存属性，
    getattr(args, f, None) 既非 _UNSET 也不会进入分支。
    """
    for f in SAVE_FIELDS:
        if getattr(args, f, None) is not _UNSET:
            continue
        if f in ("bench", "agent"):
            print("错误: 缺少必传参数 bench/agent", file=sys.stderr)
            sys.exit(1)
        elif f == "concurrency":
            # 兼容同义词，可省略（缺省时仅用 window_size）
            setattr(args, f, None)
        elif f == "window_size":
            # 主并发参数：缺省 = 0 = 不限制（全部并行）
            setattr(args, f, 0)
        elif f in ("ee", "set"):
            setattr(args, f, [])
        elif f == "pre":
            setattr(args, f, True)
        elif f == "async_mode":
            setattr(args, f, False)
        elif f == "poll_interval":
            setattr(args, f, 10)
        elif f == "poll_timeout":
            setattr(args, f, 600)
        else:
            # 字符串类字段：dataset/split/image/cluster/model/api_key/namespace/
            # cpus/memory/companion/config/user_id/base_url/tasks
            setattr(args, f, "")


def build_rc_cmd(config, split, task_id, experiment_id):
    cmd = [
        "rc", "agent", "run",
        "--bench", config.bench,
        "--split", split,
        "--task", task_id,
        "--experiment-id", experiment_id,
        "--agent", config.agent,
    ]
    if getattr(config, "pre", True):
        cmd += ["--pre"]
    if config.image:
        cmd += ["--image", config.image]
    if config.cluster:
        cmd += ["--cluster", config.cluster]
    if config.model:
        cmd += ["--model", config.model]
    if config.api_key:
        cmd += ["--api-key", config.api_key]
    if getattr(config, "namespace", ""):
        cmd += ["--namespace", config.namespace]
    if getattr(config, "cpus", ""):
        cmd += ["--cpus", config.cpus]
    if getattr(config, "memory", ""):
        cmd += ["--memory", config.memory]
    if getattr(config, "companion", ""):
        cmd += ["--with", config.companion]
    if getattr(config, "config", ""):
        cmd += ["--config", config.config]
    if getattr(config, "async_mode", False):
        cmd += ["--async"]
    if getattr(config, "user_id", ""):
        cmd += ["--user-id", config.user_id]
    if getattr(config, "base_url", ""):
        cmd += ["--base-url", config.base_url]
    auto_clear = getattr(config, "auto_clear", _UNSET)
    if auto_clear is not _UNSET and auto_clear is not None:
        cmd += ["--auto-clear", str(auto_clear)]
    for ee in config.ee:
        cmd += ["--ee", ee]
    for s in getattr(config, "set", []):
        cmd += ["--set", s]
    return cmd


def run_single_task(result_json, experiment_id, log_dir, config, total_tasks, task_id, idx, total):
    global dispatched_count
    with count_lock:
        dispatched_count += 1
        current = dispatched_count
    print(f"[{idx}/{total}] Dispatching {task_id}  (#{current} dispatched)")

    log_file = Path(log_dir) / f"{task_id}.log"
    update_task_result(result_json, task_id, total_tasks, "dispatched")

    try:
        cmd = build_rc_cmd(config, config.split, task_id, experiment_id)
        with open(log_file, "w", buffering=1, encoding="utf-8") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
            exit_code = proc.wait()
    except Exception as e:
        log_file.write_text(f"Exception: {e}\n", encoding="utf-8")
        exit_code = 1

    log_content = log_file.read_text(encoding="utf-8")
    # 复用 parse_job_from_log 的正则逻辑；此处仍需完整 log_content 用于下方错误行解析
    job_name_parsed, sandbox_id_parsed = parse_job_from_log(experiment_id, task_id)
    sandbox_id = sandbox_id_parsed if sandbox_id_parsed else ""
    job_name = job_name_parsed if job_name_parsed else ""

    if job_name:
        query_and_update_task(
            result_json, experiment_id, task_id, total_tasks,
            job_name, sandbox_id, config.api_key,
            config.poll_interval, config.poll_timeout,
        )
        tag = "OK" if exit_code == 0 else "FAIL"
    else:
        err_msg = ""
        if exit_code != 0:
            for line in log_content.splitlines():
                if re.search(r"error|rate limit|quota", line, re.IGNORECASE):
                    err_msg = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
                    break
        extra = {"exception_message": err_msg} if err_msg else {}
        update_task_result(result_json, task_id, total_tasks, "error", sandbox_id, job_name, extra)
        tag = "FAIL"

    print(f"[{idx}/{total}] [{tag}]  {task_id}  sandbox={sandbox_id}")


def resolve_concurrency(config, total_tasks):
    """计算滑动窗口的并发上限。

    - window_size 为主：表示全局同时在飞的任务数（滑动窗口大小）。
      window_size <= 0 表示不限制（= total_tasks，全部一起跑）。
    - concurrency 为兼容同义词（旧用法）；两者同时给定时取较小值，避免超限。
    """
    ws = getattr(config, "window_size", 0) or 0
    if ws <= 0:
        cap = total_tasks
    else:
        cap = ws
    cc = getattr(config, "concurrency", None)
    if cc:  # 兼容旧 --concurrency：同时给定时收紧到较小值
        cap = min(cap, cc)
    return max(1, cap)


def run_window(result_json, experiment_id, log_dir, config, total_tasks, task_batch, offset, total):
    """滑动窗口并发派发：维持固定并发上限，一个任务完成立刻补充下一个。

    通过 ThreadPoolExecutor(max_workers=N) 实现——线程池天然在任务完成时
    复用线程调度下一个，无需手动分批 barrier。task_batch 通常就是全部待跑任务。
    """
    max_workers = resolve_concurrency(config, len(task_batch))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                run_single_task, result_json, experiment_id, log_dir,
                config, total_tasks, task_id, offset + idx + 1, total,
            ): task_id
            for idx, task_id in enumerate(task_batch)
        }
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[ERROR] {task_id}: {e}")


def cmd_run(args):
    global dispatched_count

    if args.tasks:
        all_tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
        print(f"使用手动指定的 {len(all_tasks)} 个任务")
    else:
        if not args.dataset or not args.split:
            print("错误: 未指定 --tasks 时，--dataset 和 --split 为必传参数", file=sys.stderr)
            sys.exit(1)
        all_tasks = fetch_task_list(args.dataset, args.split, args.api_key)

    total_tasks = len(all_tasks)

    dataset_short = args.dataset.split("/")[-1]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_id = f"{dataset_short}-{ts}"
    result_json = f"./results/{experiment_id}.json"
    log_dir = f"./logs/{experiment_id}"

    if args.resume:
        json_files = sorted(glob(f"./results/{dataset_short}-*.json"), reverse=True)
        if not json_files:
            print("错误: 找不到已有的结果文件")
            sys.exit(1)
        result_json = json_files[0]
        with open(result_json) as f:
            prev = json.load(f)
        experiment_id = prev["experiment_id"]
        log_dir = f"./logs/{experiment_id}"

        done = {
            t["task_id"]
            for t in prev.get("tasks", {}).values()
            if t.get("status") in ("success", "error")
        }
        tasks = [t for t in all_tasks if t not in done]
        print(f"续跑模式: 已完成 {total_tasks - len(tasks)}, 待续跑 {len(tasks)}")
    else:
        tasks = list(all_tasks)

    if not tasks:
        print("所有任务已完成，无需续跑。")
        sys.exit(0)

    total = len(tasks)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    Path(result_json).parent.mkdir(parents=True, exist_ok=True)
    init_result_json(result_json, experiment_id, args, all_tasks)

    # 配置持久化：自动存 + 显式存
    save_config(args, f"./configs/{experiment_id}.json")
    if getattr(args, "save_config", None):
        save_config(args, args.save_config)

    concurrency_cap = resolve_concurrency(args, total)
    cap_desc = f"{concurrency_cap}" if concurrency_cap < total else "不限（全部并行）"
    print(LINE)
    print(" 全量回归")
    print(f" Bench:       {args.bench}")
    print(f" Dataset:     {args.dataset}")
    print(f" Split:       {args.split}")
    print(f" Agent:       {args.agent}")
    print(f" Model:       {args.model or '(rockcli 默认)'}")
    print(f" Image:       {args.image or '(rockcli 默认)'}")
    print(f" Cluster:     {args.cluster or '(rockcli 默认)'}")
    print(f" Experiment:  {experiment_id}")
    print(f" 任务总数:    {total}")
    print(f" 并发上限:    {cap_desc}  (滑动窗口：完成一个补一个)")
    print(f" Result:      {result_json}")
    print(f" Logs:        {log_dir}")
    print(LINE)

    dispatched_count = 0

    # 滑动窗口：全部任务一次性提交给线程池，由 max_workers 维持并发上限
    run_window(result_json, experiment_id, log_dir, args, total_tasks, tasks, 0, total)

    # 读→改→写:monitor/sync 可能并发访问该文件,整段纳入跨进程文件锁,写走原子写。
    with _file_lock(result_json):
        with open(result_json) as f:
            data = json.load(f)
        data["finished_at"] = now_iso()
        _atomic_write_json(result_json, data)

    s = data["summary"]
    rewards = [t["reward"] for t in data.get("tasks", {}).values() if t.get("reward") is not None]

    print()
    print(LINE)
    print(f" 实验 ID:     {data['experiment_id']}")
    print(f" 总任务:      {s['total']}")
    print(f" 成功:        {s['success']}")
    print(f" 失败:        {s['error']}")
    print(f" 未完成:      {s['pending'] + s['dispatched']}")
    if rewards:
        avg = sum(rewards) / len(rewards)
        print(f" 平均 Reward: {avg:.4f}  (共 {len(rewards)} 个)")
    print(f" Result:      {result_json}")
    print(LINE)


# ─── report 子命令 ───

def print_report_header(data, result_path):
    started = data.get("started_at", "")
    finished = data.get("finished_at", "")
    duration_str = "-"
    if started and finished:
        try:
            t0 = datetime.fromisoformat(started)
            t1 = datetime.fromisoformat(finished)
            duration_str = format_duration((t1 - t0).total_seconds() * 1000)
        except Exception:
            pass

    print(LINE)
    print(" 回归报告")
    print(LINE)
    print(f" Experiment:  {data.get('experiment_id', '-')}")
    print(f" Bench:       {data.get('bench', '-')}")
    print(f" Dataset:     {data.get('dataset', '-')}")
    print(f" Split:       {data.get('split', '-')}")
    print(f" Agent:       {data.get('agent', '-')}")
    print(f" Model:       {data.get('model') or '(默认)'}")
    print(f" Image:       {data.get('image') or '(默认)'}")
    print(f" Cluster:     {data.get('cluster') or '(默认)'}")
    print(f" 开始时间:    {started[:19] if started else '-'}")
    print(f" 结束时间:    {finished[:19] if finished else '(进行中)'}")
    print(f" 总耗时:      {duration_str}")
    print(f" 文件:        {result_path}")
    print(LINE)


def print_status_summary(tasks):
    total = len(tasks)
    if total == 0:
        print(" (无任务)")
        return

    counts = Counter(t.get("status", "pending") for t in tasks.values())
    status_order = ["success", "error", "dispatched", "pending"]

    print()
    print(" 状态汇总")
    print("-" * 70)
    print(f" {'状态':<14} {'数量':>6}  {'占比':>7}  分布")
    print("-" * 70)
    max_count = max(counts.values()) if counts else 1
    for s in status_order:
        c = counts.get(s, 0)
        if c == 0:
            continue
        pct = c / total * 100
        bar = make_bar(c, max_count, 30)
        print(f" {s:<14} {c:>6}  {pct:>6.1f}%  {bar}")
    print("-" * 70)
    print(f" {'TOTAL':<14} {total:>6}  100.0%")
    print("-" * 70)


def print_reward_distribution(tasks):
    rewards = sorted(t["reward"] for t in tasks.values() if t.get("reward") is not None)
    if not rewards:
        print()
        print(" Reward 分布: 暂无数据")
        return

    n = len(rewards)
    mean = sum(rewards) / n
    variance = sum((r - mean) ** 2 for r in rewards) / n if n > 1 else 0
    std = math.sqrt(variance)

    print()
    print(f" Reward 分布 (N={n})")
    print("-" * 70)
    print(f" Min:     {min(rewards):.4f}        P25:    {percentile(rewards, 0.25):.4f}")
    print(f" Median:  {percentile(rewards, 0.5):.4f}        P75:    {percentile(rewards, 0.75):.4f}")
    print(f" Mean:    {mean:.4f}        Max:    {max(rewards):.4f}")
    print(f" Std:     {std:.4f}")
    print("-" * 70)

    bins = [0] * 10
    for r in rewards:
        idx = min(int(r * 10), 9)
        bins[idx] += 1
    max_bin = max(bins) if bins else 1

    print(" 直方图:")
    for i in range(10):
        if bins[i] == 0:
            continue
        lo = i * 0.1
        hi = (i + 1) * 0.1
        bracket = "]" if i == 9 else ")"
        bar = make_bar(bins[i], max_bin, 20)
        pct = bins[i] / n * 100 if n > 0 else 0
        print(f" [{lo:.1f}, {hi:.1f}{bracket}  {bar:<20} {bins[i]:>4}  ({pct:>5.1f}%)")
    print("-" * 70)


def print_duration_distribution(tasks):
    durations = sorted(t["duration_ms"] for t in tasks.values() if t.get("duration_ms") is not None)
    if not durations:
        return

    n = len(durations)
    mean = sum(durations) / n

    print()
    print(f" 耗时分布 (N={n})")
    print("-" * 70)
    print(f" Min:     {format_duration(min(durations)):<14}  P25:    {format_duration(percentile(durations, 0.25))}")
    print(f" Median:  {format_duration(percentile(durations, 0.5)):<14}  P75:    {format_duration(percentile(durations, 0.75))}")
    print(f" Mean:    {format_duration(mean):<14}  Max:    {format_duration(max(durations))}")
    print("-" * 70)


def print_exception_breakdown(tasks):
    error_tasks = [t for t in tasks.values() if t.get("status") == "error"]
    if not error_tasks:
        return

    by_type = Counter(t.get("exception_type") or "(未知)" for t in error_tasks)

    print()
    print(f" 异常分类 (共 {len(error_tasks)} 个)")
    print("-" * 70)
    print(f" {'#':<4} {'异常类型':<30} {'数量':>6}  {'占比':>7}  示例任务")
    print("-" * 70)
    for i, (exc_type, count) in enumerate(by_type.most_common(), 1):
        pct = count / len(error_tasks) * 100
        sample = next(t["task_id"] for t in error_tasks if (t.get("exception_type") or "(未知)") == exc_type)
        print(f" {i:<4} {exc_type:<30} {count:>6}  {pct:>6.1f}%  {sample}")
    print("-" * 70)


def print_unfinished_warning(tasks, experiment_id):
    dispatched = [t for t in tasks.values() if t.get("status") == "dispatched"]
    if not dispatched:
        return
    print()
    print(f" !! {len(dispatched)} 个任务仍在 dispatched 状态（轮询超时或中断）")
    print(f"    运行 sync 刷新: python3 regression.py sync {experiment_id}")


def generate_html_report(data):
    """生成自包含的 HTML 可视化报告"""
    tasks = data.get("tasks", {})
    summary = data.get("summary", {})
    experiment_id = data.get("experiment_id", "unknown")

    rewards = sorted(t["reward"] for t in tasks.values() if t.get("reward") is not None)
    durations = sorted(t["duration_ms"] for t in tasks.values() if t.get("duration_ms") is not None)
    error_tasks = [t for t in tasks.values() if t.get("status") == "error"]

    reward_stats = {}
    if rewards:
        n = len(rewards)
        mean = sum(rewards) / n
        variance = sum((r - mean) ** 2 for r in rewards) / n if n > 1 else 0
        reward_stats = {
            "count": n, "mean": round(mean, 4),
            "min": round(min(rewards), 4), "max": round(max(rewards), 4),
            "median": round(percentile(rewards, 0.5), 4),
            "p25": round(percentile(rewards, 0.25), 4),
            "p75": round(percentile(rewards, 0.75), 4),
            "std": round(math.sqrt(variance), 4),
        }

    bins = [0] * 10
    for r in rewards:
        bins[min(int(r * 10), 9)] += 1

    duration_stats = {}
    if durations:
        n = len(durations)
        duration_stats = {
            "count": n,
            "mean": round(sum(durations) / n),
            "min": min(durations), "max": max(durations),
            "median": round(percentile(durations, 0.5)),
            "p25": round(percentile(durations, 0.25)),
            "p75": round(percentile(durations, 0.75)),
        }

    exc_counts = dict(Counter(
        t.get("exception_type") or "(未知)" for t in error_tasks
    ).most_common(15))

    msg_counter = Counter()
    msg_samples = {}
    for t in error_tasks:
        key = normalize_exception_msg(t.get("exception_message", ""))
        msg_counter[key] += 1
        if key not in msg_samples:
            msg_samples[key] = t["task_id"]

    started = data.get("started_at", "")
    finished = data.get("finished_at", "")
    duration_str = "-"
    if started and finished:
        try:
            t0 = datetime.fromisoformat(started)
            t1 = datetime.fromisoformat(finished)
            duration_str = format_duration((t1 - t0).total_seconds() * 1000)
        except Exception:
            pass

    report_data = json.dumps({
        "experiment_id": experiment_id,
        "bench": data.get("bench", "-"),
        "dataset": data.get("dataset", "-"),
        "split": data.get("split", "-"),
        "agent": data.get("agent", "-"),
        "model": data.get("model") or "(默认)",
        "cluster": data.get("cluster") or "(默认)",
        "image": data.get("image") or "(默认)",
        "started_at": started[:19] if started else "-",
        "finished_at": finished[:19] if finished else "(进行中)",
        "duration_str": duration_str,
        "summary": summary,
        "reward_stats": reward_stats,
        "reward_bins": bins,
        "duration_stats": duration_stats,
        "exceptions": exc_counts,
        "error_messages": [
            {"msg": msg, "count": count, "sample": msg_samples[msg]}
            for msg, count in msg_counter.most_common(10)
        ],
        "tasks": [
            {
                "task_id": t.get("task_id", ""),
                "status": t.get("status", "pending"),
                "reward": t.get("reward"),
                "duration_ms": t.get("duration_ms"),
                "exception_type": t.get("exception_type") or "",
                "sandbox_id": t.get("sandbox_id") or "",
                "job_name": t.get("job_name") or "",
                "agent_name": t.get("agent_name") or "",
            }
            for t in tasks.values()
        ],
    }, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Regression Report — {experiment_id}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Fira+Code:wght@400;500;600&family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after {{ margin:0; padding:0; box-sizing:border-box; }}

:root {{
  --bg: #070b14;
  --surface: #0d1219;
  --card: #131a28;
  --card-hover: #182035;
  --border: #1c2540;
  --border-accent: #2a3555;
  --text: #d8dde8;
  --text-2: #7a889f;
  --text-3: #4a5568;
  --success: #10b981;
  --success-bg: #10b98118;
  --error: #f43f5e;
  --error-bg: #f43f5e18;
  --warning: #f59e0b;
  --warning-bg: #f59e0b18;
  --info: #3b82f6;
  --info-bg: #3b82f618;
  --accent: #8b5cf6;
  --accent-bg: #8b5cf618;
  --font-display: 'Bebas Neue', 'Impact', sans-serif;
  --font-mono: 'Fira Code', 'Menlo', monospace;
  --font-body: 'Barlow', 'Helvetica Neue', sans-serif;
  --radius: 10px;
  --radius-sm: 6px;
}}

html {{ font-size: 14px; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  min-height: 100vh;
  line-height: 1.5;
}}

/* Top glow line */
body::before {{
  content: '';
  position: fixed; top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--accent), var(--info), var(--success), var(--warning), var(--error));
  z-index: 100;
}}

.container {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem 2.5rem 4rem;
}}

/* ─── Header ─── */
.header {{
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--border);
  animation: fadeIn 0.6s ease;
}}
.header-left h1 {{
  font-family: var(--font-display);
  font-size: 2.8rem;
  letter-spacing: 0.08em;
  color: var(--text);
  line-height: 1;
  margin-bottom: 0.5rem;
}}
.header-left h1 span {{ color: var(--accent); }}
.header-meta {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.25rem 2rem;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--text-2);
}}
.header-meta .label {{ color: var(--text-3); margin-right: 0.5em; }}
.header-right {{
  text-align: right;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--text-2);
  flex-shrink: 0;
  margin-left: 2rem;
}}
.status-badge {{
  display: inline-block;
  padding: 0.15em 0.7em;
  border-radius: 20px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
.status-badge.finished {{ background: var(--success-bg); color: var(--success); }}
.status-badge.running {{ background: var(--warning-bg); color: var(--warning); }}

/* ─── Status Strip ─── */
.status-strip {{
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 2rem;
  animation: fadeIn 0.8s ease;
}}
.status-strip div {{ transition: width 1s ease; }}
.status-strip .s-success {{ background: var(--success); }}
.status-strip .s-error {{ background: var(--error); }}
.status-strip .s-dispatched {{ background: var(--warning); }}
.status-strip .s-pending {{ background: var(--border); }}

/* ─── KPI Cards ─── */
.kpi-row {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}}
.kpi {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.2rem 1.4rem;
  animation: slideUp 0.6s ease backwards;
}}
.kpi:nth-child(2) {{ animation-delay: 0.05s; }}
.kpi:nth-child(3) {{ animation-delay: 0.1s; }}
.kpi:nth-child(4) {{ animation-delay: 0.15s; }}
.kpi:nth-child(5) {{ animation-delay: 0.2s; }}
.kpi:nth-child(6) {{ animation-delay: 0.25s; }}
.kpi .kpi-label {{
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.4rem;
}}
.kpi .kpi-value {{
  font-family: var(--font-display);
  font-size: 2.6rem;
  letter-spacing: 0.04em;
  line-height: 1;
}}
.kpi .kpi-sub {{
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-2);
  margin-top: 0.3rem;
}}
.kpi.success .kpi-value {{ color: var(--success); }}
.kpi.error .kpi-value {{ color: var(--error); }}
.kpi.warning .kpi-value {{ color: var(--warning); }}
.kpi.accent .kpi-value {{ color: var(--accent); }}
.kpi.info .kpi-value {{ color: var(--info); }}

/* ─── Panels ─── */
.panels {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}}
@media (max-width: 900px) {{ .panels {{ grid-template-columns: 1fr; }} }}
.panel {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem;
  animation: slideUp 0.7s ease backwards;
}}
.panel:nth-child(2) {{ animation-delay: 0.1s; }}
.panel-title {{
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 1.2rem;
  display: flex;
  align-items: center;
  gap: 0.5em;
}}
.panel-title::before {{
  content: '';
  display: inline-block;
  width: 3px; height: 12px;
  background: var(--accent);
  border-radius: 2px;
}}

/* ─── Donut (CSS conic-gradient) ─── */
.donut-wrap {{
  display: flex;
  align-items: center;
  gap: 2rem;
}}
.donut {{
  width: 160px; height: 160px;
  border-radius: 50%;
  position: relative;
  flex-shrink: 0;
}}
.donut::after {{
  content: '';
  position: absolute;
  inset: 30px;
  background: var(--card);
  border-radius: 50%;
}}
.donut-center {{
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 1;
}}
.donut-center .big {{
  font-family: var(--font-display);
  font-size: 2rem;
  letter-spacing: 0.04em;
}}
.donut-center .small {{
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--text-2);
}}
.donut-legend {{ font-family: var(--font-mono); font-size: 0.78rem; }}
.donut-legend .row {{
  display: flex;
  align-items: center;
  gap: 0.6em;
  margin-bottom: 0.5rem;
}}
.donut-legend .dot {{
  width: 10px; height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.donut-legend .count {{
  margin-left: auto;
  color: var(--text-2);
  min-width: 3em;
  text-align: right;
}}

/* ─── Histogram ─── */
.histogram {{
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 140px;
  padding-top: 1rem;
}}
.hist-bar-wrap {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
}}
.hist-bar {{
  width: 100%;
  border-radius: 3px 3px 0 0;
  background: linear-gradient(180deg, var(--accent) 0%, var(--info) 100%);
  min-height: 2px;
  animation: growUp 0.8s ease backwards;
  position: relative;
}}
.hist-bar:hover {{ filter: brightness(1.3); cursor: default; }}
.hist-bar-wrap:nth-child(2) .hist-bar {{ animation-delay: 0.05s; }}
.hist-bar-wrap:nth-child(3) .hist-bar {{ animation-delay: 0.1s; }}
.hist-bar-wrap:nth-child(4) .hist-bar {{ animation-delay: 0.15s; }}
.hist-bar-wrap:nth-child(5) .hist-bar {{ animation-delay: 0.2s; }}
.hist-bar-wrap:nth-child(6) .hist-bar {{ animation-delay: 0.25s; }}
.hist-bar-wrap:nth-child(7) .hist-bar {{ animation-delay: 0.3s; }}
.hist-bar-wrap:nth-child(8) .hist-bar {{ animation-delay: 0.35s; }}
.hist-bar-wrap:nth-child(9) .hist-bar {{ animation-delay: 0.4s; }}
.hist-bar-wrap:nth-child(10) .hist-bar {{ animation-delay: 0.45s; }}
.hist-count {{
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--text-2);
  margin-bottom: 4px;
}}
.hist-label {{
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: var(--text-3);
  margin-top: 6px;
  white-space: nowrap;
}}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.2rem 1rem;
  margin-top: 1rem;
  font-family: var(--font-mono);
  font-size: 0.75rem;
}}
.stats-grid .sl {{ color: var(--text-3); }}
.stats-grid .sv {{ color: var(--text); text-align: right; }}

/* ─── Exception Table ─── */
.full-panel {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem;
  margin-bottom: 1rem;
  animation: slideUp 0.8s ease backwards;
  animation-delay: 0.2s;
}}
.exc-table {{
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 0.78rem;
}}
.exc-table th {{
  text-align: left;
  color: var(--text-3);
  font-weight: 500;
  padding: 0.5rem 0.8rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}}
.exc-table td {{
  padding: 0.5rem 0.8rem;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}}
.exc-table tr:last-child td {{ border-bottom: none; }}
.exc-table tr:hover {{ background: var(--card-hover); }}
.exc-bar {{
  height: 6px;
  background: var(--error);
  border-radius: 3px;
  opacity: 0.7;
}}

/* ─── Task Table ─── */
.task-controls {{
  display: flex;
  gap: 0.8rem;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}}
.task-search {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.5rem 0.8rem;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  width: 260px;
  outline: none;
  transition: border-color 0.2s;
}}
.task-search:focus {{ border-color: var(--accent); }}
.filter-btn {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.4rem 0.8rem;
  color: var(--text-2);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  cursor: pointer;
  transition: all 0.2s;
}}
.filter-btn:hover {{ border-color: var(--text-2); color: var(--text); }}
.filter-btn.active {{ border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }}
.task-table {{
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 0.75rem;
}}
.task-table th {{
  text-align: left;
  color: var(--text-3);
  font-weight: 500;
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}}
.task-table th:hover {{ color: var(--text); }}
.task-table th .sort-arrow {{ color: var(--accent); margin-left: 0.3em; }}
.task-table td {{
  padding: 0.45rem 0.6rem;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}}
.task-table tr:hover {{ background: var(--card-hover); }}
.task-table .badge {{
  display: inline-block;
  padding: 0.1em 0.5em;
  border-radius: 4px;
  font-size: 0.68rem;
  font-weight: 600;
}}
.badge-success {{ background: var(--success-bg); color: var(--success); }}
.badge-error {{ background: var(--error-bg); color: var(--error); }}
.badge-dispatched {{ background: var(--warning-bg); color: var(--warning); }}
.badge-pending {{ background: var(--border); color: var(--text-3); }}
.task-count {{
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-3);
  margin-left: auto;
}}

/* ─── Animations ─── */
@keyframes fadeIn {{
  from {{ opacity: 0; }}
  to {{ opacity: 1; }}
}}
@keyframes slideUp {{
  from {{ opacity: 0; transform: translateY(16px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes growUp {{
  from {{ transform: scaleY(0); transform-origin: bottom; }}
  to {{ transform: scaleY(1); transform-origin: bottom; }}
}}

/* ─── Tooltip ─── */
[data-tip] {{ position: relative; }}
[data-tip]:hover::after {{
  content: attr(data-tip);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--surface);
  border: 1px solid var(--border-accent);
  color: var(--text);
  padding: 0.3em 0.6em;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 0.68rem;
  white-space: nowrap;
  z-index: 10;
  pointer-events: none;
}}

/* ─── Scrollbar ─── */
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: var(--surface); }}
::-webkit-scrollbar-thumb {{ background: var(--border-accent); border-radius: 3px; }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <header class="header" id="header"></header>

  <!-- Status Strip -->
  <div class="status-strip" id="statusStrip"></div>

  <!-- KPI Row -->
  <div class="kpi-row" id="kpiRow"></div>

  <!-- Charts -->
  <div class="panels" id="panels"></div>

  <!-- Exceptions -->
  <div class="full-panel" id="excPanel" style="display:none"></div>

  <!-- Task Table -->
  <div class="full-panel" id="taskPanel"></div>

</div>

<script>
const D = {report_data};

// ─── Helpers ───
function fmt(v, d=4) {{ return v == null ? '-' : Number(v).toFixed(d); }}
function fmtDur(ms) {{
  if (ms == null) return '-';
  const s = ms / 1000;
  if (s < 60) return s.toFixed(1) + 's';
  const m = Math.floor(s / 60);
  if (m < 60) return m + 'm ' + Math.round(s % 60) + 's';
  return Math.floor(m/60) + 'h ' + (m%60) + 'm';
}}
function pct(n, t) {{ return t ? (n/t*100).toFixed(1) + '%' : '0%'; }}
function el(tag, cls, html) {{
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}}

// ─── Header ───
(() => {{
  const h = document.getElementById('header');
  const isFinished = D.finished_at && D.finished_at !== '(进行中)';
  h.innerHTML = `
    <div class="header-left">
      <h1><span>REG</span> ${{D.experiment_id}}</h1>
      <div class="header-meta">
        <div><span class="label">BENCH</span> ${{D.bench}}</div>
        <div><span class="label">DATASET</span> ${{D.dataset}}</div>
        <div><span class="label">SPLIT</span> ${{D.split}}</div>
        <div><span class="label">AGENT</span> ${{D.agent}}</div>
        <div><span class="label">MODEL</span> ${{D.model}}</div>
        <div><span class="label">CLUSTER</span> ${{D.cluster}}</div>
      </div>
    </div>
    <div class="header-right">
      <span class="status-badge ${{isFinished ? 'finished' : 'running'}}">
        ${{isFinished ? 'FINISHED' : 'RUNNING'}}
      </span>
      <div style="margin-top:0.5rem">
        <div>开始 ${{D.started_at}}</div>
        <div>结束 ${{D.finished_at}}</div>
        <div>耗时 ${{D.duration_str}}</div>
      </div>
    </div>`;
}})();

// ─── Status Strip ───
(() => {{
  const s = D.summary;
  const t = s.total || 1;
  const strip = document.getElementById('statusStrip');
  [{{'k':'success','c':'s-success'}},{{'k':'error','c':'s-error'}},{{'k':'dispatched','c':'s-dispatched'}},{{'k':'pending','c':'s-pending'}}].forEach(x => {{
    if (s[x.k] > 0) {{
      const d = document.createElement('div');
      d.className = x.c;
      d.style.width = (s[x.k] / t * 100) + '%';
      d.setAttribute('data-tip', x.k + ': ' + s[x.k]);
      strip.appendChild(d);
    }}
  }});
}})();

// ─── KPIs ───
(() => {{
  const s = D.summary;
  const total = s.total || 0;
  const passRate = total ? ((s.success || 0) / total * 100).toFixed(1) : '0';
  const row = document.getElementById('kpiRow');

  const cards = [
    {{ label: 'TOTAL', value: total, cls: '', sub: `${{s.success||0}} ok / ${{s.error||0}} err / ${{(s.dispatched||0)+(s.pending||0)}} other` }},
    {{ label: 'PASS RATE', value: passRate + '%', cls: parseFloat(passRate) >= 50 ? 'success' : 'error', sub: `${{s.success||0}} / ${{total}}` }},
    {{ label: 'AVG REWARD', value: D.reward_stats.mean != null ? D.reward_stats.mean.toFixed(4) : '-', cls: 'accent', sub: D.reward_stats.count ? `N=${{D.reward_stats.count}}  std=${{D.reward_stats.std}}` : '暂无数据' }},
    {{ label: 'MEDIAN REWARD', value: D.reward_stats.median != null ? D.reward_stats.median.toFixed(4) : '-', cls: 'info', sub: D.reward_stats.count ? `P25=${{D.reward_stats.p25}}  P75=${{D.reward_stats.p75}}` : '' }},
    {{ label: 'AVG DURATION', value: D.duration_stats.mean != null ? fmtDur(D.duration_stats.mean) : '-', cls: 'warning', sub: D.duration_stats.count ? `N=${{D.duration_stats.count}}  min=${{fmtDur(D.duration_stats.min)}}  max=${{fmtDur(D.duration_stats.max)}}` : '' }},
    {{ label: 'ERRORS', value: s.error || 0, cls: (s.error || 0) > 0 ? 'error' : '', sub: Object.keys(D.exceptions).length + ' 种异常类型' }},
  ];

  cards.forEach(c => {{
    const d = el('div', 'kpi ' + c.cls);
    d.innerHTML = `<div class="kpi-label">${{c.label}}</div><div class="kpi-value">${{c.value}}</div><div class="kpi-sub">${{c.sub}}</div>`;
    row.appendChild(d);
  }});
}})();

// ─── Panels: Donut + Histogram ───
(() => {{
  const panels = document.getElementById('panels');
  const s = D.summary;
  const total = s.total || 1;

  // Donut Panel
  const donutPanel = el('div', 'panel');
  const items = [
    {{ name: 'Success', count: s.success||0, color: 'var(--success)' }},
    {{ name: 'Error', count: s.error||0, color: 'var(--error)' }},
    {{ name: 'Dispatched', count: s.dispatched||0, color: 'var(--warning)' }},
    {{ name: 'Pending', count: s.pending||0, color: 'var(--border-accent)' }},
  ].filter(x => x.count > 0);

  let gradParts = [];
  let cum = 0;
  items.forEach(item => {{
    const pctVal = item.count / total * 100;
    gradParts.push(`${{item.color}} ${{cum}}% ${{cum + pctVal}}%`);
    cum += pctVal;
  }});
  const grad = `conic-gradient(${{gradParts.join(', ')}})`;

  const passRate = total ? ((s.success||0) / total * 100).toFixed(1) : '0';
  let legendHtml = items.map(it =>
    `<div class="row"><span class="dot" style="background:${{it.color}}"></span>${{it.name}}<span class="count">${{it.count}} (${{pct(it.count, total)}})</span></div>`
  ).join('');

  donutPanel.innerHTML = `
    <div class="panel-title">状态分布</div>
    <div class="donut-wrap">
      <div class="donut" style="background:${{grad}}">
        <div class="donut-center"><span class="big">${{passRate}}%</span><span class="small">PASS RATE</span></div>
      </div>
      <div class="donut-legend">${{legendHtml}}</div>
    </div>`;
  panels.appendChild(donutPanel);

  // Histogram Panel
  const histPanel = el('div', 'panel');
  const bins = D.reward_bins || [];
  const maxBin = Math.max(...bins, 1);
  const rn = D.reward_stats.count || 0;

  let barsHtml = bins.map((b, i) => {{
    if (b === 0) return '';
    const h = Math.max(b / maxBin * 120, 2);
    const lo = (i * 0.1).toFixed(1);
    const hi = ((i+1) * 0.1).toFixed(1);
    const bracket = i === 9 ? ']' : ')';
    const tipText = `[${{lo}}, ${{hi}}${{bracket}}: ${{b}} (${{rn ? (b/rn*100).toFixed(1) : 0}}%)`;
    return `<div class="hist-bar-wrap"><span class="hist-count">${{b}}</span><div class="hist-bar" style="height:${{h}}px" data-tip="${{tipText}}"></div><span class="hist-label">${{lo}}</span></div>`;
  }}).filter(Boolean).join('');

  let statsHtml = '';
  if (D.reward_stats.count) {{
    const rs = D.reward_stats;
    statsHtml = `<div class="stats-grid">
      <span class="sl">Min</span><span class="sv">${{rs.min}}</span>
      <span class="sl">P25</span><span class="sv">${{rs.p25}}</span>
      <span class="sl">Median</span><span class="sv">${{rs.median}}</span>
      <span class="sl">P75</span><span class="sv">${{rs.p75}}</span>
      <span class="sl">Mean</span><span class="sv">${{rs.mean}}</span>
      <span class="sl">Max</span><span class="sv">${{rs.max}}</span>
      <span class="sl">Std</span><span class="sv">${{rs.std}}</span>
      <span class="sl">N</span><span class="sv">${{rs.count}}</span>
    </div>`;
  }}

  histPanel.innerHTML = `
    <div class="panel-title">Reward 分布</div>
    <div class="histogram">${{barsHtml}}</div>
    ${{statsHtml}}`;
  panels.appendChild(histPanel);
}})();

// ─── Exception Panel ───
(() => {{
  const exc = D.exceptions || {{}};
  const keys = Object.keys(exc);
  if (keys.length === 0) return;

  const panel = document.getElementById('excPanel');
  panel.style.display = 'block';
  const maxCount = Math.max(...Object.values(exc), 1);
  const totalErrors = Object.values(exc).reduce((a,b) => a+b, 0);

  let rows = keys.map(k =>
    `<tr>
      <td>${{k}}</td>
      <td style="text-align:right">${{exc[k]}}</td>
      <td style="text-align:right">${{pct(exc[k], totalErrors)}}</td>
      <td style="width:40%"><div class="exc-bar" style="width:${{exc[k]/maxCount*100}}%"></div></td>
    </tr>`
  ).join('');

  let msgRows = '';
  if (D.error_messages && D.error_messages.length) {{
    msgRows = `
      <div class="panel-title" style="margin-top:1.5rem">去重错误消息 Top 10</div>
      <table class="exc-table">
        <thead><tr><th style="width:50px">#</th><th>消息模式</th><th style="width:60px;text-align:right">次数</th><th>示例</th></tr></thead>
        <tbody>${{D.error_messages.map((m, i) =>
          `<tr><td>${{i+1}}</td><td style="max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" data-tip="${{m.msg.replace(/"/g, '&quot;')}}">${{m.msg}}</td><td style="text-align:right">${{m.count}}</td><td>${{m.sample}}</td></tr>`
        ).join('')}}</tbody>
      </table>`;
  }}

  panel.innerHTML = `
    <div class="panel-title">异常分类 (${{totalErrors}} 个错误)</div>
    <table class="exc-table">
      <thead><tr><th>异常类型</th><th style="text-align:right;width:60px">数量</th><th style="text-align:right;width:60px">占比</th><th style="width:40%">分布</th></tr></thead>
      <tbody>${{rows}}</tbody>
    </table>
    ${{msgRows}}`;
}})();

// ─── Task Table ───
(() => {{
  const panel = document.getElementById('taskPanel');
  const tasks = D.tasks || [];
  let sortKey = 'task_id', sortAsc = true, filterStatus = 'all', searchText = '';

  function render() {{
    let filtered = tasks.filter(t => {{
      if (filterStatus !== 'all' && t.status !== filterStatus) return false;
      if (searchText && !t.task_id.toLowerCase().includes(searchText.toLowerCase())) return false;
      return true;
    }});

    filtered.sort((a, b) => {{
      let va = a[sortKey], vb = b[sortKey];
      if (va == null) va = sortKey === 'reward' || sortKey === 'duration_ms' ? -Infinity : '';
      if (vb == null) vb = sortKey === 'reward' || sortKey === 'duration_ms' ? -Infinity : '';
      if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      return sortAsc ? va - vb : vb - va;
    }});

    const badgeCls = {{'success':'badge-success','error':'badge-error','dispatched':'badge-dispatched','pending':'badge-pending'}};
    const arrow = sortAsc ? '↑' : '↓';

    const statuses = ['all', 'success', 'error', 'dispatched', 'pending'];
    const btnHtml = statuses.map(s =>
      `<button class="filter-btn ${{filterStatus===s?'active':''}}" data-filter="${{s}}">${{s === 'all' ? '全部' : s}}</button>`
    ).join('');

    panel.innerHTML = `
      <div class="panel-title">任务列表</div>
      <div class="task-controls">
        <input type="text" class="task-search" placeholder="搜索任务 ID..." value="${{searchText}}">
        ${{btnHtml}}
        <span class="task-count">${{filtered.length}} / ${{tasks.length}}</span>
      </div>
      <div style="max-height:500px;overflow-y:auto">
      <table class="task-table">
        <thead><tr>
          ${{['task_id','status','reward','duration_ms','exception_type','agent_name','job_name'].map(k => {{
            const label = {{'task_id':'TASK ID','status':'STATUS','reward':'REWARD','duration_ms':'DURATION','exception_type':'EXCEPTION','agent_name':'AGENT','job_name':'JOB'}}[k];
            return `<th data-sort="${{k}}">${{label}}${{sortKey===k ? '<span class="sort-arrow">'+arrow+'</span>' : ''}}</th>`;
          }}).join('')}}
        </tr></thead>
        <tbody>
          ${{filtered.map(t => `<tr>
            <td>${{t.task_id}}</td>
            <td><span class="badge ${{badgeCls[t.status]||'badge-pending'}}">${{t.status}}</span></td>
            <td>${{t.reward != null ? t.reward.toFixed(4) : '-'}}</td>
            <td>${{fmtDur(t.duration_ms)}}</td>
            <td data-tip="${{t.exception_type}}">${{t.exception_type || '-'}}</td>
            <td>${{t.agent_name || '-'}}</td>
            <td>${{t.job_name || '-'}}</td>
          </tr>`).join('')}}
        </tbody>
      </table>
      </div>`;

    panel.querySelector('.task-search').addEventListener('input', e => {{
      searchText = e.target.value;
      render();
    }});
    panel.querySelectorAll('.filter-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        filterStatus = btn.dataset.filter;
        render();
      }});
    }});
    panel.querySelectorAll('th[data-sort]').forEach(th => {{
      th.addEventListener('click', () => {{
        const k = th.dataset.sort;
        if (sortKey === k) sortAsc = !sortAsc;
        else {{ sortKey = k; sortAsc = true; }}
        render();
      }});
    }});
  }}

  render();
}})();
</script>
</body>
</html>'''
    return html


def cmd_report(args):
    result_path, data = resolve_experiment(args)
    tasks = data.get("tasks", {})
    fmt = getattr(args, "format", "text")

    if fmt == "json":
        rewards = sorted(t["reward"] for t in tasks.values() if t.get("reward") is not None)
        durations = sorted(t["duration_ms"] for t in tasks.values() if t.get("duration_ms") is not None)
        error_tasks = [t for t in tasks.values() if t.get("status") == "error"]
        report = {
            "experiment_id": data.get("experiment_id"),
            "summary": data.get("summary"),
            "reward": {
                "count": len(rewards),
                "mean": sum(rewards) / len(rewards) if rewards else None,
                "min": min(rewards) if rewards else None,
                "max": max(rewards) if rewards else None,
                "median": percentile(rewards, 0.5) if rewards else None,
                "p25": percentile(rewards, 0.25) if rewards else None,
                "p75": percentile(rewards, 0.75) if rewards else None,
            },
            "duration": {
                "count": len(durations),
                "mean_ms": sum(durations) / len(durations) if durations else None,
                "min_ms": min(durations) if durations else None,
                "max_ms": max(durations) if durations else None,
                "median_ms": percentile(durations, 0.5) if durations else None,
            },
            "exceptions": dict(Counter(t.get("exception_type") or "(未知)" for t in error_tasks).most_common()),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    if fmt == "html":
        import webbrowser
        html = generate_html_report(data)
        experiment_id = data.get("experiment_id", "report")
        out_path = Path(f"./results/{experiment_id}.html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"HTML 报告已生成: {out_path}")
        if getattr(args, "open", False):
            webbrowser.open(f"file://{out_path.resolve()}")
        return

    print_report_header(data, result_path)
    print_status_summary(tasks)
    print_reward_distribution(tasks)
    print_duration_distribution(tasks)
    print_exception_breakdown(tasks)
    print_unfinished_warning(tasks, data.get("experiment_id", ""))
    print()


# ─── sync 子命令 ───

def cmd_sync(args):
    result_path, data = resolve_experiment(args)
    experiment_id = data["experiment_id"]
    api_key = args.api_key
    tasks = data.get("tasks", {})
    total_tasks = data.get("summary", {}).get("total", len(tasks))
    dry_run = getattr(args, "dry_run", False)

    # 对结果文件中 job_name 缺失的任务，先尝试从日志回填 job_name/sandbox_id。
    # regression.py 中途重启后，部分任务服务端已派发（日志里有 job_name），
    # 但结果文件尚未写入，此处回填避免误标为派发失败。
    recovered = 0
    for task_id, task in tasks.items():
        if task.get("job_name"):
            continue
        log_job, log_sandbox = parse_job_from_log(experiment_id, task_id)
        if not log_job:
            continue
        recovered += 1
        task["job_name"] = log_job
        if log_sandbox and not task.get("sandbox_id"):
            task["sandbox_id"] = log_sandbox
        if not dry_run:
            update_task_result(
                result_path, task_id, total_tasks, task.get("status", "dispatched"),
                log_sandbox or "", log_job,
            )
    if recovered:
        print(f"从日志恢复 job_name: {recovered} 个任务")

    tasks_to_sync = []
    for task_id, task in tasks.items():
        if not task.get("job_name"):
            continue
        if task["status"] == "dispatched":
            tasks_to_sync.append(task)
        elif task["status"] == "success" and task.get("reward") is None:
            tasks_to_sync.append(task)
        elif getattr(args, "force", False):
            tasks_to_sync.append(task)

    no_job_dispatched = [
        t for t in tasks.values()
        if t["status"] == "dispatched"
        and not t.get("job_name")
        and not _is_dispatch_fresh(t)  # 刚派发(<300s)的任务跳过,避免误判正在派发中的任务
    ]
    # 被新鲜度守卫跳过、暂时保持 dispatched 的任务数（仅用于提示）
    fresh_skipped = sum(
        1 for t in tasks.values()
        if t["status"] == "dispatched"
        and not t.get("job_name")
        and _is_dispatch_fresh(t)
    )

    if not tasks_to_sync and not no_job_dispatched:
        if fresh_skipped:
            print(f"所有任务状态已是最新，无需同步。(跳过 {fresh_skipped} 个刚派发(<300s)的任务)")
        else:
            print("所有任务状态已是最新，无需同步。")
        return

    print(f"实验: {experiment_id}")
    print(f"需要同步: {len(tasks_to_sync)} 个任务 (有 job_name)")
    if no_job_dispatched:
        print(f"派发失败: {len(no_job_dispatched)} 个任务 (无 job_name)")
    if fresh_skipped:
        print(f"跳过 {fresh_skipped} 个刚派发(<300s)的任务")
    print()

    if dry_run:
        print("[DRY RUN] 以下任务将被同步:")
        for t in tasks_to_sync:
            print(f"  {t['task_id']}  job={t['job_name']}  status={t['status']}")
        for t in no_job_dispatched:
            print(f"  {t['task_id']}  (无 job_name, 将标记为 error)")
        return

    updated = 0
    concurrency = getattr(args, "concurrency", 10)
    still_running_tasks = []

    def sync_one(task):
        view_data = _fetch_view_data(experiment_id, task["job_name"], api_key)
        return task["task_id"], view_data

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(sync_one, t): t for t in tasks_to_sync}
        for future in as_completed(futures):
            task = futures[future]
            try:
                task_id, view_data = future.result()
                extra = extract_task_extra(view_data)
                new_status = "error" if extra.get("n_errors", 0) > 0 else "success"
                has_result = (extra.get("n_completed", 0) + extra.get("n_errors", 0) > 0
                              or extra.get("finished_at"))
                if has_result:
                    update_task_result(result_path, task_id, total_tasks, new_status,
                                      task.get("sandbox_id", ""), task["job_name"], extra)
                    old_status = task["status"]
                    reward = extra.get("reward", "?")
                    print(f"  [SYNCED] {task_id}  {old_status} -> {new_status}  reward={reward}")
                    updated += 1
                else:
                    still_running_tasks.append(task)
            except Exception as e:
                print(f"  [ERROR] {task['task_id']}: {e}")

    # Fallback: for tasks whose job_name was not found on the remote (corrupted by
    # failed retries), discover the correct job via remote experiment job listing.
    if still_running_tasks and api_key:
        print(f"\n  {len(still_running_tasks)} 个任务本地 job 未在远端找到，尝试远端发现...")
        remote_jobs = _fetch_experiment_jobs(experiment_id, api_key)
        if remote_jobs:
            remote_job_names = [j["name"] for j in remote_jobs]
            task_job_map = _discover_task_job_mapping(experiment_id, api_key, remote_job_names, concurrency)
            for task in still_running_tasks:
                task_id = task["task_id"]
                if task_id in task_job_map:
                    correct_job, view_data = task_job_map[task_id]
                    extra = extract_task_extra(view_data)
                    new_status = "error" if extra.get("n_errors", 0) > 0 else "success"
                    has_result = (extra.get("n_completed", 0) + extra.get("n_errors", 0) > 0
                                  or extra.get("finished_at"))
                    if has_result:
                        update_task_result(result_path, task_id, total_tasks, new_status,
                                          task.get("sandbox_id", ""), correct_job, extra)
                        old_status = task["status"]
                        reward = extra.get("reward", "?")
                        print(f"  [DISCOVERED] {task_id}  {old_status} -> {new_status}  reward={reward}  (job={correct_job})")
                        updated += 1
                    else:
                        print(f"  [STILL RUNNING] {task_id}  job={correct_job}")
                else:
                    print(f"  [STILL RUNNING] {task_id}  job={task['job_name']}")
        else:
            for task in still_running_tasks:
                print(f"  [STILL RUNNING] {task['task_id']}  job={task['job_name']}")

    for t in no_job_dispatched:
        update_task_result(result_path, t["task_id"], total_tasks, "error",
                          extra={"exception_message": "dispatch 失败: 未获取到 job_name"})
        print(f"  [MARKED ERROR] {t['task_id']}  (无 job_name)")
        updated += 1

    print()
    print(f"同步完成: {updated} 个任务已更新")
    print(f"结果文件: {result_path}")


# ─── diagnose 子命令 ───

def diagnose_overview(data, args):
    tasks = data.get("tasks", {})
    experiment_id = data.get("experiment_id", "")

    status_filter = getattr(args, "status", None)
    exc_filter = getattr(args, "exception_type", None)

    filtered = {}
    for tid, t in tasks.items():
        if status_filter and t.get("status") != status_filter:
            continue
        if exc_filter and t.get("exception_type") != exc_filter:
            continue
        filtered[tid] = t

    if not filtered:
        print("没有匹配的任务。")
        return

    error_tasks = [t for t in filtered.values() if t.get("status") == "error"]
    dispatched_tasks = [t for t in filtered.values() if t.get("status") == "dispatched"]

    print(LINE)
    print(f" 失败排查: {experiment_id}")
    print(LINE)

    if error_tasks:
        by_type = Counter(t.get("exception_type") or "(未知)" for t in error_tasks)
        print()
        print(f" 按异常类型分组 ({len(error_tasks)} 个错误)")
        print("-" * 70)
        print(f" {'#':<4} {'异常类型':<30} {'数量':>6}  示例任务")
        print("-" * 70)
        for i, (exc_type, count) in enumerate(by_type.most_common(), 1):
            samples = [t["task_id"] for t in error_tasks if (t.get("exception_type") or "(未知)") == exc_type][:2]
            print(f" {i:<4} {exc_type:<30} {count:>6}  {', '.join(samples)}")
        print("-" * 70)

        msg_counter = Counter()
        msg_samples = {}
        for t in error_tasks:
            key = normalize_exception_msg(t.get("exception_message", ""))
            msg_counter[key] += 1
            if key not in msg_samples:
                msg_samples[key] = t["task_id"]

        print()
        print(f" 去重错误消息 Top 10")
        print("-" * 70)
        for i, (msg, count) in enumerate(msg_counter.most_common(10), 1):
            print(f" {i:>2}. [{count:>3}x] {msg}")
            print(f"      示例: {msg_samples[msg]}")
        print("-" * 70)

    if dispatched_tasks:
        print()
        print(f" 卡住的任务 ({len(dispatched_tasks)} 个 dispatched)")
        print("-" * 70)
        print(f" {'任务 ID':<30} {'Job Name':<16} {'Dispatched At':<22} 有日志")
        print("-" * 70)
        for t in dispatched_tasks[:20]:
            job = t.get("job_name") or "(无)"
            dispatched_at = (t.get("dispatched_at") or "")[:19]
            log_path = Path(f"./logs/{experiment_id}/{t['task_id']}.log")
            has_log = "Yes" if log_path.exists() else "No"
            print(f" {t['task_id']:<30} {job:<16} {dispatched_at:<22} {has_log}")
        if len(dispatched_tasks) > 20:
            print(f" ... 还有 {len(dispatched_tasks) - 20} 个")
        print("-" * 70)
        print(f" 建议: 先运行 sync，再 retry --filter dispatched")

    print()


def diagnose_single_task(data, args):
    tasks = data.get("tasks", {})
    task_id = args.task
    task = tasks.get(task_id)
    if not task:
        print(f"错误: 任务 {task_id} 不在实验结果中", file=sys.stderr)
        sys.exit(1)

    experiment_id = data.get("experiment_id", "")
    api_key = args.api_key

    print(LINE)
    print(f" 任务详情: {task_id}")
    print(LINE)
    print(f" Status:      {task.get('status')}")
    print(f" Sandbox:     {task.get('sandbox_id') or '-'}")
    print(f" Job:         {task.get('job_name') or '-'}")
    print(f" Agent:       {task.get('agent_name') or '-'}")
    print(f" Reward:      {task.get('reward') if task.get('reward') is not None else '-'}")
    print(f" Duration:    {format_duration(task.get('duration_ms'))}")
    print(f" Dispatched:  {(task.get('dispatched_at') or '-')[:19]}")
    print(f" Finished:    {(task.get('finished_at') or '-')[:19]}")
    print(f" Trials:      {task.get('n_trials', 0)}  Completed: {task.get('n_completed', 0)}  Errors: {task.get('n_errors', 0)}")
    if task.get("exception_type"):
        print(f" Exception:   {task.get('exception_type')}")
        msg = task.get("exception_message", "")
        if len(msg) > 200:
            msg = msg[:200] + "..."
        print(f" Message:     {msg}")
    print(LINE)

    tail = getattr(args, "tail", 30)
    log_path = Path(f"./logs/{experiment_id}/{task_id}.log")
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        show = lines[-tail:] if len(lines) > tail else lines
        print()
        print(f" 本地日志 (最后 {len(show)} 行): {log_path}")
        print("-" * 70)
        for line in show:
            print(f" {line}")
        print("-" * 70)
    else:
        print(f"\n 本地日志不存在: {log_path}")

    job_name = task.get("job_name")
    if not job_name:
        return

    if getattr(args, "remote", False):
        print()
        print(f" 远程日志 (rc agent fs)")
        print("-" * 70)
        cmd = ["rc", "agent", "fs", "ls", "-e", experiment_id, "-j", job_name,
               "-t", task_id, "--pre"]
        if api_key:
            cmd += ["--api-key", api_key]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0 and proc.stdout.strip():
            print(" 文件列表:")
            for line in proc.stdout.strip().splitlines():
                print(f"   {line}")
            print()
            log_candidates = ["run.log", "agent.log", "log.txt", "agent/log.txt", "agent/run.log"]
            for log_name in log_candidates:
                cat_cmd = ["rc", "agent", "fs", "cat", log_name, "-e", experiment_id,
                           "-j", job_name, "-t", task_id, "--pre"]
                if api_key:
                    cat_cmd += ["--api-key", api_key]
                cat_proc = subprocess.run(cat_cmd, capture_output=True, text=True, timeout=60)
                if cat_proc.returncode == 0 and cat_proc.stdout.strip():
                    log_lines = cat_proc.stdout.strip().splitlines()
                    show = log_lines[-tail:] if len(log_lines) > tail else log_lines
                    print(f" 远程日志 {log_name} (最后 {len(show)} 行):")
                    for line in show:
                        print(f"   {line}")
                    break
        else:
            print(f" 远程文件查询失败: {proc.stderr.strip()}")
        print("-" * 70)

    if getattr(args, "trajectory", False):
        print()
        print(f" 执行轨迹")
        print("-" * 70)
        cmd = ["rc", "agent", "view", "-j", job_name, "--trajectory", "--pre", "-e", experiment_id]
        if api_key:
            cmd += ["--api-key", api_key]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            print(proc.stdout[:3000] if len(proc.stdout) > 3000 else proc.stdout)
        else:
            print(f" 查询失败: {proc.stderr.strip()}")
        print("-" * 70)

    if getattr(args, "artifacts", False):
        print()
        print(f" 产物清单")
        print("-" * 70)
        cmd = ["rc", "agent", "fs", "artifacts", "-e", experiment_id, "-j", job_name,
               "-t", task_id, "--pre"]
        if api_key:
            cmd += ["--api-key", api_key]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            print(proc.stdout)
        else:
            print(f" 查询失败: {proc.stderr.strip()}")
        print("-" * 70)


def cmd_diagnose(args):
    _, data = resolve_experiment(args)
    if getattr(args, "task", None):
        diagnose_single_task(data, args)
    else:
        diagnose_overview(data, args)


# ─── retry 子命令 ───

def select_retry_tasks(data, filter_mode, exception_type=None):
    result = []
    for task_id, task in data.get("tasks", {}).items():
        if filter_mode == "error" and task["status"] != "error":
            continue
        if filter_mode == "dispatched" and task["status"] != "dispatched":
            continue
        if filter_mode == "all-failed" and task["status"] not in ("error", "dispatched"):
            continue
        if exception_type and task.get("exception_type") != exception_type:
            continue
        result.append(task_id)
    return result


def cmd_retry(args):
    global dispatched_count

    _, data = resolve_experiment(args)
    orig_experiment_id = data["experiment_id"]

    if args.tasks:
        retry_tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    else:
        retry_tasks = select_retry_tasks(data, args.filter, getattr(args, "exception_type", None))

    if not retry_tasks:
        print("没有匹配的任务需要重跑。")
        sys.exit(0)

    split = args.split or data.get("split", "")
    if not split:
        print("错误: 需要指定 --split", file=sys.stderr)
        sys.exit(1)
    args.split = split

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if getattr(args, "same_experiment", False):
        experiment_id = orig_experiment_id
    else:
        experiment_id = f"{orig_experiment_id}-retry-{ts}"

    result_json = f"./results/{experiment_id}.json"
    log_dir = f"./logs/{experiment_id}"

    total_tasks = len(retry_tasks)
    total = total_tasks

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    Path(result_json).parent.mkdir(parents=True, exist_ok=True)
    init_result_json(result_json, experiment_id, args, retry_tasks,
                     extra_fields={"retry_of": orig_experiment_id})

    # 配置持久化：自动存 + 显式存
    save_config(args, f"./configs/{experiment_id}.json")
    if getattr(args, "save_config", None):
        save_config(args, args.save_config)

    print(LINE)
    print(" Retry 重跑")
    print(f" 原实验:      {orig_experiment_id}")
    print(f" 新实验:      {experiment_id}")
    concurrency_cap = resolve_concurrency(args, total)
    cap_desc = f"{concurrency_cap}" if concurrency_cap < total else "不限（全部并行）"
    print(f" Bench:       {args.bench}")
    print(f" Split:       {split}")
    print(f" Agent:       {args.agent}")
    print(f" Filter:      {args.filter}")
    print(f" 重跑任务:    {total}")
    print(f" 并发上限:    {cap_desc}  (滑动窗口：完成一个补一个)")
    print(f" Result:      {result_json}")
    print(f" Logs:        {log_dir}")
    print(LINE)

    dispatched_count = 0

    # 滑动窗口：全部任务一次性提交给线程池，由 max_workers 维持并发上限
    run_window(result_json, experiment_id, log_dir, args, total_tasks, retry_tasks, 0, total)

    # 读→改→写:retry 时 monitor/sync 可能并发,整段纳入跨进程文件锁,写走原子写。
    with _file_lock(result_json):
        with open(result_json) as f:
            result_data = json.load(f)
        result_data["finished_at"] = now_iso()
        _atomic_write_json(result_json, result_data)

    s = result_data["summary"]
    rewards = [t["reward"] for t in result_data.get("tasks", {}).values() if t.get("reward") is not None]

    print()
    print(LINE)
    print(f" Retry 完成")
    print(f" 实验 ID:     {experiment_id}")
    print(f" 总任务:      {s['total']}")
    print(f" 成功:        {s['success']}")
    print(f" 失败:        {s['error']}")
    print(f" 未完成:      {s['pending'] + s['dispatched']}")
    if rewards:
        avg = sum(rewards) / len(rewards)
        print(f" 平均 Reward: {avg:.4f}  (共 {len(rewards)} 个)")
    print(f" Result:      {result_json}")
    print(LINE)


# ─── argparse ───

def add_common_args(parser):
    parser.add_argument("experiment", nargs="?", default=None, help="实验 ID 或结果文件路径（不传则使用最新的）")
    parser.add_argument("--api-key", default="", help="API 密钥")


def add_rc_args(parser, include_api_key=False):
    """添加 rc agent run 的全部参数（透传给 rockcli）"""
    rc = parser.add_argument_group("rockcli 参数（透传给 rc agent run）")
    rc.add_argument("--bench", default=_UNSET, help="Bench 模板名称")
    rc.add_argument("--dataset", default=_UNSET, help="数据集名称")
    rc.add_argument("--split", default=_UNSET, help="数据集 split")
    rc.add_argument("--agent", default=_UNSET, help="Agent 名称")
    rc.add_argument("--image", default=_UNSET, help="Docker 镜像")
    rc.add_argument("--cluster", default=_UNSET, help="集群标识")
    rc.add_argument("--model", default=_UNSET, help="模型名称")
    if include_api_key:
        rc.add_argument("--api-key", default=_UNSET, help="API 密钥")
    rc.add_argument("--ee", action=_AppendUnsetAction, default=_UNSET, help="沙箱环境变量 (KEY=VALUE)，可多次指定")
    rc.add_argument("--set", action=_AppendUnsetAction, default=_UNSET, help="YAML 字段覆盖 (path=value)，可多次指定")
    rc.add_argument("--pre", action="store_true", default=_UNSET, help="使用预发环境（默认启用）")
    rc.add_argument("--no-pre", action="store_false", dest="pre", help="使用正式环境")
    rc.add_argument("--namespace", default=_UNSET, help="ROCK 项目空间")
    rc.add_argument("--cpus", default=_UNSET, help="CPU 规格（Core）")
    rc.add_argument("--memory", default=_UNSET, help="内存规格（GiB）")
    rc.add_argument("--with-companion", dest="companion", default=_UNSET, help="启用陪跑助手（如 claude-code）")
    rc.add_argument("--config", default=_UNSET, help="JobConfig YAML 配置文件路径（Config 模式）")
    rc.add_argument("--async-mode", action="store_true", default=_UNSET, help="异步模式：提取 sandbox_id 后退出")
    rc.add_argument("--user-id", default=_UNSET, help="用户 ID（工号）")
    rc.add_argument("--base-url", default=_UNSET, help="服务端地址")
    rc.add_argument("--auto-clear", type=int, default=_UNSET,
                    help="自动清理时间（秒，透传到 rc agent run --auto-clear）")


def add_run_args(parser):
    add_rc_args(parser, include_api_key=True)

    ctrl = parser.add_argument_group("调度控制参数")
    ctrl.add_argument("--concurrency", type=int, default=_UNSET, help="（兼容旧参数）并发数；与 --window-size 同时给定时取较小值")
    ctrl.add_argument("--window-size", type=int, default=_UNSET, help="全局并发上限（滑动窗口：完成一个补一个）；0=不限制")
    ctrl.add_argument("--resume", action="store_true", help="续跑模式")
    ctrl.add_argument("--tasks", default=_UNSET, help="手动指定任务列表（逗号分隔）")
    ctrl.add_argument("--poll-interval", type=int, default=_UNSET, help="轮询间隔秒数")
    ctrl.add_argument("--poll-timeout", type=int, default=_UNSET, help="轮询超时秒数")
    ctrl.add_argument("--from-config", dest="from_config", default=None,
                      help="从 JSON 配置文件加载参数（CLI 显式参数覆盖 JSON）")
    ctrl.add_argument("--save-config", dest="save_config", default=None,
                      help="额外把本次配置保存到指定 JSON 路径")


def parse_args():
    parser = argparse.ArgumentParser(
        description="通用全量回归脚本 — 基于 rockcli",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # run
    p_run = subparsers.add_parser("run", help="执行回归任务")
    add_run_args(p_run)

    # report
    p_report = subparsers.add_parser("report", help="查看结果报告")
    add_common_args(p_report)
    p_report.add_argument("--format", choices=["text", "json", "html"], default="text", help="输出格式")
    p_report.add_argument("--open", action="store_true", help="生成 HTML 后自动在浏览器中打开")

    # sync
    p_sync = subparsers.add_parser("sync", help="从服务端同步最新状态")
    add_common_args(p_sync)
    p_sync.add_argument("--force", action="store_true", help="强制重新同步所有任务")
    p_sync.add_argument("--dry-run", action="store_true", help="只显示变更不写入")
    p_sync.add_argument("--concurrency", type=int, default=10, help="同步并发数")

    # diagnose
    p_diag = subparsers.add_parser("diagnose", help="失败排查")
    add_common_args(p_diag)
    p_diag.add_argument("--task", help="指定单个任务深入排查")
    p_diag.add_argument("--remote", action="store_true", help="拉取远程日志")
    p_diag.add_argument("--trajectory", action="store_true", help="查看执行轨迹")
    p_diag.add_argument("--artifacts", action="store_true", help="查看产物清单")
    p_diag.add_argument("--status", choices=["error", "dispatched", "success"], help="按状态过滤")
    p_diag.add_argument("--exception", dest="exception_type", help="按异常类型过滤")
    p_diag.add_argument("--tail", type=int, default=30, help="本地日志显示行数")

    # retry
    p_retry = subparsers.add_parser("retry", help="重跑失败任务")
    add_common_args(p_retry)
    add_rc_args(p_retry)
    p_retry.add_argument("--concurrency", type=int, default=_UNSET, help="（兼容旧参数）并发数；与 --window-size 同时给定时取较小值")
    p_retry.add_argument("--window-size", type=int, default=_UNSET, help="全局并发上限（滑动窗口：完成一个补一个）；0=不限制")
    p_retry.add_argument("--filter", choices=["error", "dispatched", "all-failed"], default="all-failed",
                         help="重跑范围: error/dispatched/all-failed")
    p_retry.add_argument("--exception-type", help="只重跑特定异常类型")
    p_retry.add_argument("--tasks", default=_UNSET, help="手动指定重跑任务列表（逗号分隔）")
    p_retry.add_argument("--same-experiment", action="store_true", help="沿用原实验 ID")
    p_retry.add_argument("--poll-interval", type=int, default=_UNSET, help="轮询间隔秒数")
    p_retry.add_argument("--poll-timeout", type=int, default=_UNSET, help="轮询超时秒数")
    p_retry.add_argument("--from-config", dest="from_config", default=None,
                         help="从 JSON 配置文件加载参数（CLI 显式参数覆盖 JSON）")
    p_retry.add_argument("--save-config", dest="save_config", default=None,
                         help="额外把本次配置保存到指定 JSON 路径")

    # 向后兼容：无子命令但有 --bench 时走 run
    if len(sys.argv) > 1 and sys.argv[1] not in ("run", "report", "sync", "diagnose", "retry", "-h", "--help"):
        if "--bench" in sys.argv:
            sys.argv.insert(1, "run")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    return args


def main():
    args = parse_args()
    if getattr(args, "from_config", None):
        apply_config(args, args.from_config)
    normalize_args(args)
    dispatch = {
        "run": cmd_run,
        "report": cmd_report,
        "sync": cmd_sync,
        "diagnose": cmd_diagnose,
        "retry": cmd_retry,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
