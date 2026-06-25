#!/usr/bin/env python3
"""通用全量回归脚本 — 基于 rockcli 实现任意 template + 数据集的全量回归

子命令:
    run       执行回归任务

用法:
    python3 regression.py run --bench aone-bench --dataset alibaba/aone-bench-java100 \\
        --split delivery_0609-cn --agent claude-code --concurrency 20 --window-size 0
"""

import argparse
import fcntl
import json
import os
import re
import time
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

# ─── 全局状态 ───

json_lock = threading.Lock()
dispatched_count = 0
count_lock = threading.Lock()

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
    if auto_clear is not _UNSET and auto_clear is not None and auto_clear != "":
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

    dataset_short = (args.dataset.split("/")[-1] if args.dataset
                     else args.bench.split("/")[-1])
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

# ─── argparse ───

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

    # 向后兼容：无子命令但有 --bench 时走 run
    if len(sys.argv) > 1 and sys.argv[1] not in ("run", "-h", "--help"):
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
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
