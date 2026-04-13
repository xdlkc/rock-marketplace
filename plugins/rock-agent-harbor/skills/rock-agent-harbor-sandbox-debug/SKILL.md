---
name: rock-agent-harbor-sandbox-debug
description: 分析和排查运行在 ROCK 沙箱（sandbox）中的 Harbor 任务。当用户提供沙箱 ID 并询问 harbor 任务状态、进度、日志、reward、agent 执行情况，或遇到 job 失败、trial 异常、reward 为 0、agent 崩溃、verifier 错误等问题时使用。触发词：沙箱里跑的 harbor、查一下 sandbox 里的 harbor job、看看 trial 状态、bench 跑到哪了、查 reward、看 agent 日志、harbor run 失败、bench 跑不通、agent 没有得分、trial exception、verifier 报错、container 挂了、reward.txt 为空、debug harbor、排查 bench。
---

# Rock Agent Harbor Sandbox Debug Skill

通过 `rockcli` 查询和排查运行在 ROCK 沙箱中的 Harbor 任务，最终产出一份落盘的详细报告。

## 背景

Harbor 是运行在 ROCK 沙箱中的 Agent Benchmark 评测框架。用户通过 `rockcli` 管理沙箱，Harbor 在沙箱内逐 Trial 执行 Agent → Verifier 流程，产物落盘到 `/data/logs/user-defined/`（平台启动）或 `/tmp/harbor/jobs/`（本地 `harbor run`）。

## 重要原则

**拿到足够信息就停止查询。** 不要陷入"文件不在预期位置就全盘搜索"的循环。判断标准：
- ROCK 平台任务（`/data/logs/user-defined/`）：`.out` 文件包含完整运行日志，能看到 reward 就够了
- harbor run 任务（`/tmp/harbor/jobs/`）：`result.json` + `trial.log` + `exception.txt` 就够了
- 如果 `result.json` 不存在但 `.out` 或 `job.log` 能说明情况，**不必继续找**，直接用现有信息出报告

---

## Step 1：确认沙箱 ID 和 jobs 目录

```bash
# 查看沙箱存活状态
rockcli sandbox <id> status

# 同时检查两个路径
rockcli sandbox <id> exec 'echo "=== /tmp/harbor/jobs/ ==="; ls -lt /tmp/harbor/jobs/ 2>/dev/null | head -10; echo "=== /data/logs/user-defined/ ==="; ls -lt /data/logs/user-defined/ 2>/dev/null | head -10'
```

**两类启动方式对应不同路径：**

| 启动方式 | jobs 目录 | 配置文件 | 运行日志 |
|---------|----------|---------|---------|
| `harbor run` 直接运行 | `/tmp/harbor/jobs/` | `config.json` | `job.log` |
| `rockcli agent run`（ROCK 平台） | `/data/logs/user-defined/jobs/` | `<job_name>.yaml` | `<job_name>.out`（完整） |

如果用户没给沙箱 ID，直接问。

---

## Step 2：定位目标 Job

用户没有指定 job 时，取最新有内容的一个（空目录跳过）。

```bash
# harbor run 路径：找最新非空的 job
rockcli sandbox <id> exec 'for d in $(ls -t /tmp/harbor/jobs/); do if [ "$(ls /tmp/harbor/jobs/$d 2>/dev/null)" ]; then echo $d; break; fi; done'

# ROCK 平台路径：列出 .yaml 文件
rockcli sandbox <id> exec 'ls -lt /data/logs/user-defined/*.yaml 2>/dev/null | head -5'
```

---

## Step 3：读取 Job 信息

根据路径类型选择对应命令：

### /tmp/harbor/jobs/ 路径

```bash
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/config.json'
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/result.json 2>/dev/null || echo "no result yet"'
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/job.log 2>/dev/null'
```

### /data/logs/user-defined/ 路径（ROCK 平台）

```bash
# 配置（agent、model、dataset）
rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.yaml'

# 完整运行日志（含进度、reward、时间线）
rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.out'

# result.json（可能不存在，不要为此继续搜索）
rockcli sandbox <id> exec 'cat /data/logs/user-defined/jobs/<job_name>/result.json 2>/dev/null || echo "no result.json"'
```

**`.out` 文件足以判断任务是否完成**（含 reward 行、完成时间、trial 名），不要因为 `result.json` 不存在就全盘搜索。

---

## Step 4：逐 Trial 分析

**Trial 文件结构（/tmp/harbor/jobs/ 路径）：**
```
<trial_name>/
├── result.json          # 完整结果（阶段时间、reward、异常）
├── trial.log            # 简短摘要（失败时有错误原因）
├── exception.txt        # 完整异常栈
├── agent/setup/stdout.txt   # Agent 安装日志
├── agent/setup/return-code.txt
├── verifier/reward.txt
├── verifier/test-stdout.txt
├── verifier/test-stderr.txt
└── agent/trajectory.json    # Agent 执行轨迹（ATIF 格式，若有）
```

```bash
# 列出 trials
rockcli sandbox <id> exec 'ls /tmp/harbor/jobs/<job_name>/ 2>/dev/null || ls /data/logs/user-defined/jobs/<job_name>/ 2>/dev/null'

# 批量查看所有 trial 状态（快速）
rockcli sandbox <id> exec 'for t in /tmp/harbor/jobs/<job_name>/*/; do echo "=== $(basename $t) ==="; cat "$t/result.json" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(\"reward:\", d.get(\"verifier_result\"), \"exception:\", bool(d.get(\"exception_info\")))" 2>/dev/null || cat "$t/trial.log" 2>/dev/null | head -3; done'
```

**result.json 关键字段说明：**

| 字段 | 含义 | 异常信号 |
|------|------|---------|
| `exception_info` | 异常类型和消息 | 非 null 说明有未捕获异常 |
| `verifier_result.rewards` | 各项评分 | 全 0 或 null 说明 verifier 未运行 |
| `agent_result` | Agent 执行结果 | null 说明 agent 未正常完成 |
| `agent_execution.duration_sec` | Agent 运行时长 | 极短（<5s）说明提前退出 |
| `environment_setup` | 环境启动耗时 | 极长说明镜像构建或启动问题 |
| `started_at` / `finished_at` | 开始/结束时间 | finished_at 为 null 说明未完成 |

**判断 Trial 当前阶段（从 result.json）：**
- `environment_setup` 有值，`agent_setup` 为 null → 环境启动中
- `agent_setup` 有值，`agent_execution` 为 null → Agent 安装中
- `agent_execution` 有值，`verifier` 为 null → Agent 执行中
- `verifier` 有值，`finished_at` 为 null → Verifier 运行中
- `finished_at` 有值 → 已完成

---

## Step 5：深入调试（发现问题时）

当发现异常、reward 为 0 或任务失败时，进一步排查：

### 读取详细日志

```bash
# 1. 如果有 exception.txt，先读它
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/<trial_name>/exception.txt'

# 2. Verifier 输出（测试脚本的实际运行结果）
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/<trial_name>/verifier/test-stdout.txt'
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/<trial_name>/verifier/test-stderr.txt'

# 3. Trial 主日志（先搜关键词）
rockcli sandbox <id> exec 'grep -i "error\|exception\|failed\|traceback" /tmp/harbor/jobs/<job_name>/<trial_name>/trial.log | tail -50'
```

### 检查 Docker Container 状态

Harbor Docker container 命名规则：`hb__<environment_name>`（小写）

```bash
# 列出所有 Harbor 相关 container
rockcli sandbox <id> exec 'docker ps -a | grep "hb__"'

# 查看 container 详情
rockcli sandbox <id> exec 'docker inspect <container_name> | python3 -c "
import json, sys
data = json.load(sys.stdin)[0]
state = data[\"State\"]
print(f\"Status: {state[chr(39)]Status{chr(39)}}\")
print(f\"ExitCode: {state[chr(39)]ExitCode{chr(39)}}\")
print(f\"OOMKilled: {state[chr(39)]OOMKilled{chr(39)}}\")
"'

# 查看 container 最近日志
rockcli sandbox <id> exec 'docker logs <container_name> --tail 100'
```

### 查看 Agent 执行轨迹（按需）

用户想了解 agent 做了什么时才查。

```bash
rockcli sandbox <id> exec 'cat /path/to/trial/agent/trajectory.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
steps = d.get(\"steps\", [])
print(f\"共 {len(steps)} 步\")
for i, s in enumerate(steps[:20]):
    tool = s.get(\"tool\", \"\") or s.get(\"action\", \"\")
    summary = s.get(\"observation\", \"\") or s.get(\"result\", \"\")
    print(f\"  [{i+1}] {tool}: {str(summary)[:100]}\")
"'
```

---

## Step 6：生成报告（必须输出并保存到本地文件）

**每次分析结束必须：**
1. 在对话中输出结构化报告
2. 将报告保存到本地文件：`/tmp/harbor-report-<sandbox_id_短>-<timestamp>.md`

报告格式：

```markdown
## Harbor 任务报告

**沙箱**: <sandbox_id>
**Job**: <job_name>
**时间**: <started_at> → <finished_at 或 "运行中">
**耗时**: <duration>

### 配置
- Agent: <agent_name> (<model_name>)
- Bench: <dataset_name> v<version>（或 Task: <task_path>）
- 并发数: <n_concurrent_trials>
- Verifier 模式: <harbor/native>

### 整体结果
- 总 Trials: <n>，成功: <n>，失败: <n>
- 平均 Reward: <mean>

### Trial 明细
| Trial | 状态 | Reward | 耗时 | 问题 |
|-------|------|--------|------|------|
| <name> | ✅/❌/🔄/⚠️ | <reward> | <duration> | <issue 或 -> |

### 执行时间线
- `<HH:MM>` 环境启动完成（耗时 Xs）
- `<HH:MM>` Agent 安装完成（耗时 Xs）
- `<HH:MM>` Agent 开始执行
- `<HH:MM>` Verifier 完成，reward=<N>

### 问题分析（如有）

**[CRITICAL] 问题标题**
- 影响 trial：`<trial_name>`
- 根本原因：...
- 证据：`exception.txt` 关键日志
- 建议：...

**环境问题**（Docker/依赖/网络）
- ...

**Agent 问题**（配置/模型/token 超限）
- ...

**Verifier 问题**（测试脚本/奖励计算）
- ...

### 行动建议
1. **立即修复**：...
2. **下次运行前**：...
```

**状态图标：** ✅ 通过（reward>0）| ❌ 失败 | 🔄 运行中 | ⚠️ 完成但异常

---

## 常见故障速查

| 现象 | 失败阶段 | 典型原因 |
|------|---------|---------|
| "Docker compose command failed" / "no such host" | env_setup | 镜像拉取 DNS 失败 |
| `agent/setup/return-code.txt` = 100 | agent_setup | Agent 安装脚本失败 |
| `AgentTimeoutError` | agent_execution | Agent 超时 |
| reward=0，无异常 | verifier | Agent 完成但未解决问题 |
| `RewardFileNotFoundError` | verifier | reward.txt 不存在 |
| `no running event loop` | cleanup | Agent 超时后清理阶段崩溃（非主要失败原因） |
| reward.txt 为空或不存在 | verifier | verifier 未运行到写 reward 步骤 |
| agent_result 为 null，execution 时间极短 | agent_setup | agent 安装脚本报错 |
| 所有 trial 失败，同样的 exception | 环境层面 | 镜像/依赖/网络问题 |

## Agent 类型参考

| Agent 名 | 描述 |
|----------|------|
| `claude-code` | Claude Code CLI |
| `terminus` / `terminus-2` | Terminus 内部 agent |
| `swe-agent-internal` | 内部 SWE-Agent 实现 |
| `openhands` | OpenHands agent |
| `mini-swe-agent` | 轻量 SWE-Agent |
| `aider` | Aider coding agent |
| `opencode` | OpenCode agent |
| `oracle` | 参考 agent（已知解） |
| `nop` | 空操作（测试用） |

## 批量扫描脚本

```python
#!/usr/bin/env python3
# 用法：python3 scan_job.py ./jobs/<job_name>
import json, sys
from pathlib import Path

job_dir = Path(sys.argv[1])
trials = sorted([d for d in job_dir.iterdir() if d.is_dir()])

print(f"Job: {job_dir.name}")
print(f"{'Trial':<40} {'Reward':<8} {'Status':<12} {'Duration':<10} {'Issue'}")
print("-" * 90)

for trial_dir in trials:
    result_path = trial_dir / "result.json"
    if not result_path.exists():
        print(f"{trial_dir.name:<40} {'N/A':<8} {'NO RESULT':<12} {'-':<10}")
        continue

    try:
        r = json.loads(result_path.read_text())
    except Exception as e:
        print(f"{trial_dir.name:<40} {'ERR':<8} {'JSON ERR':<12} {'-':<10} {e}")
        continue

    reward = "N/A"
    if r.get("verifier_result") and r["verifier_result"].get("rewards"):
        rewards = r["verifier_result"]["rewards"]
        if isinstance(rewards, dict):
            reward = str(list(rewards.values())[0])
        elif isinstance(rewards, list) and rewards:
            reward = str(rewards[0])
    elif (trial_dir / "verifier" / "reward.txt").exists():
        reward = (trial_dir / "verifier" / "reward.txt").read_text().strip()

    exc = r.get("exception_info")
    status = "EXCEPTION" if exc else ("OK" if reward != "N/A" else "NO REWARD")

    duration = "-"
    if r.get("agent_execution") and r["agent_execution"].get("duration_sec"):
        duration = f"{r['agent_execution']['duration_sec']:.1f}s"

    issue = ""
    if exc:
        issue = f"{exc.get('exception_type','?')}: {str(exc.get('exception_message',''))[:50]}"

    print(f"{trial_dir.name:<40} {reward:<8} {status:<12} {duration:<10} {issue}")
```
