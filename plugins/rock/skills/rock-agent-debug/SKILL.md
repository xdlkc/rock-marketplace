---
name: rock-agent-debug
description: 使用 rockcli（rc）排查 ROCK 沙箱中运行的 Agent Job 并产出诊断报告。当用户给出沙箱或实验 ID，要查 job 的状态、日志、reward 与执行轨迹，或定位 job 失败、reward 为 0、agent 崩溃等问题时使用。
---

# Rock Agent Debug Skill

通过 `rockcli` 查询和排查运行在 ROCK 沙箱中的 Agent Job（Harbor Job / Bash Job），最终产出一份落盘的详细报告。

## 背景

ROCK 沙箱支持两种 Job 类型：

| 类型 | Config 类 | Trial 类 | 识别特征 |
|------|-----------|----------|---------|
| **Harbor Job** | `HarborJobConfig` | `HarborTrial` | 有 `orchestrator`、`datasets`、`agents`、`jobs_dir`、`experiment_id` 字段 |
| **Bash Job** | `BashJobConfig` | `BashTrial` | 有 `script` 或 `script_path` 字段，无 harbor 相关字段 |

Job 类型通过 YAML 配置自动检测：先尝试 `HarborJobConfig` 解析，失败则回退到 `BashJobConfig`。

## 两种排查路径

根据信息来源不同，排查分为两种路径：

| 路径 | 适用场景 | 核心命令 |
|------|---------|---------|
| **远程查询（推荐）** | 用户提供实验 ID + Job ID（或仅 job 名）；沙箱已停止无法 exec | `rc agent view` + `rc agent fs` |
| **沙箱内查询** | 用户提供沙箱 ID 且沙箱存活；需要更灵活的排查 | `rc sandbox <id> exec` |

**优先使用远程查询**：`agent view` 和 `agent fs` 不依赖沙箱存活状态，能直接查看 job/trial 元数据和文件，效率更高。

### 远程查询快速流程

```bash
# 1. 查看 job 状态和 trial 列表
rockcli agent view -e <exp_id> -j <job_name>

# 2. 列出 trial 文件
rockcli agent fs ls -e <exp_id> -j <job_name> -t <task_name>

# 3. 读取关键文件
rockcli agent fs cat result.json -e <exp_id> -j <job_name> -t <task_name>
rockcli agent fs cat agent/log.txt -e <exp_id> -j <job_name> -t <task_name>

# 4. 查看执行轨迹
rockcli agent view -e <exp_id> -j <job_name> --trajectory

# 5. 查看 artifacts
rockcli agent fs artifacts -e <exp_id> -j <job_name> -t <task_name>
```

## 重要原则

**拿到足够信息就停止查询。** 不要陷入"文件不在预期位置就全盘搜索"的循环。判断标准：
- Harbor Job（`/data/logs/user-defined/`）：`.out` 文件包含完整运行日志，能看到 reward 就够了
- Harbor Job（`/tmp/harbor/jobs/`）：`result.json` + `trial.log` + `exception.txt` 就够了
- Bash Job：`.out` 日志 + 脚本退出码 + artifact（如有）就够了
- 如果关键文件能说明情况，**不必继续找**，直接用现有信息出报告

---

## Step 1：确认排查入口和 Job 类型

根据用户提供的信息选择排查路径：

### 情况 A：用户提供实验 ID + Job ID（远程查询，推荐入口）

最常见的入口是 `实验 ID + Job ID` 组合。`agent view` 和 `agent fs` 都要求 `-e <experiment_id>` 定位 job，两个参数配合逐级钻取：

```bash
# 0. （可选）只有实验 ID、不知道 job 名时，先列出实验下的 jobs
rockcli agent view -e <experiment_id>

# 1. 查看 job 详情（实验 ID + Job ID）
rockcli agent view -e <experiment_id> -j <job_name>

# 2. 列出 job 文件（从文件结构判断类型）
rockcli agent fs ls -e <experiment_id> -j <job_name>
```

只有 job 名、没有实验 ID 时，先用 `rockcli agent view -E` 列出所有实验，找到对应的 `experiment_id` 再继续。

### 情况 B：用户提供沙箱 ID（沙箱内查询）

```bash
# 查看沙箱存活状态
rockcli sandbox <id> status

# 同时检查所有可能的路径
rockcli sandbox <id> exec 'echo "=== /tmp/harbor/jobs/ ==="; ls -lt /tmp/harbor/jobs/ 2>/dev/null | head -10; echo "=== /data/logs/user-defined/ ==="; ls -lt /data/logs/user-defined/ 2>/dev/null | head -10; echo "=== /data/logs/ ==="; ls -lt /data/logs/*.out /data/logs/*.log 2>/dev/null | head -10'
```

**判断 Job 类型：**
1. 读取 YAML 配置（优先）：`rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.yaml'`
2. 如果配置包含 `orchestrator`、`datasets`、`agents` → **Harbor Job**
3. 如果配置包含 `script` 或 `script_path` → **Bash Job**
4. 如果没有 YAML，只有 `/tmp/harbor/jobs/` 下的文件 → **Harbor Job**（本地 harbor run）

如果用户没给沙箱 ID 也没给实验 ID，直接问。

---

## Step 2：定位目标 Job

用户没有指定 job 时，取最新有内容的一个（空目录跳过）。

```bash
# Harbor 路径（本地 harbor run）：找最新非空的 job
rockcli sandbox <id> exec 'for d in $(ls -t /tmp/harbor/jobs/); do if [ "$(ls /tmp/harbor/jobs/$d 2>/dev/null)" ]; then echo $d; break; fi; done'

# ROCK 平台路径：列出 .yaml 配置和 .out 日志
rockcli sandbox <id> exec 'ls -lt /data/logs/user-defined/*.yaml /data/logs/user-defined/*.out 2>/dev/null | head -10'
```

---

## Step 3：读取 Job 信息

### 远程查询方式（agent view / agent fs）

适用于有 `实验 ID + Job ID` 的场景，**不依赖沙箱存活状态**：

```bash
# 查看 job 整体状态（含 tasks 列表、进度）
rockcli agent view -e <exp_id> -j <job_name>

# 列出 job 目录结构
rockcli agent fs ls -e <exp_id> -j <job_name>

# 读取 result.json
rockcli agent fs cat result.json -e <exp_id> -j <job_name> -t <task_name>

# 读取日志文件
rockcli agent fs cat agent/log.txt -e <exp_id> -j <job_name> -t <task_name>

# 查看完整执行轨迹
rockcli agent view -e <exp_id> -j <job_name> --trajectory

# 查看 trial artifacts
rockcli agent fs artifacts -e <exp_id> -j <job_name> -t <task_name>
```

### 沙箱内查询方式

#### Harbor Job

##### /tmp/harbor/jobs/ 路径（本地 harbor run）

```bash
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/config.json'
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/result.json 2>/dev/null || echo "no result yet"'
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/job.log 2>/dev/null'
```

##### /data/logs/user-defined/ 路径（ROCK 平台）

```bash
# 配置（agent、model、dataset）
rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.yaml'

# 完整运行日志（含进度、reward、时间线）
rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.out'

# result.json（可能不存在，不要为此继续搜索）
rockcli sandbox <id> exec 'cat /data/logs/user-defined/jobs/<job_name>/result.json 2>/dev/null || echo "no result.json"'
```

**`.out` 文件足以判断任务是否完成**（含 reward 行、完成时间、trial 名），不要因为 `result.json` 不存在就全盘搜索。

#### Bash Job

```bash
# 配置（script / script_path）
rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.yaml'

# 完整运行日志
rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.out'

# 检查是否有 artifact 输出
rockcli sandbox <id> exec 'ls -lt /data/logs/artifacts/ 2>/dev/null | head -10'
```

Bash Job 的特点：
- 单次脚本执行，没有 trial 概念
- 退出码 (exit code) 是判断成功/失败的关键
- 可能有 OSS artifact 输出到 `artifacts/{namespace}/{experiment_id}/{job_name}/`
- 日志直接输出到 `.out` 文件

---

## Step 4：分析结果

### Harbor Job：逐 Trial 分析

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

### Bash Job：单次执行分析

Bash Job 没有 trial 概念，是一次性的脚本执行：

```bash
# 查看退出码（.out 末尾通常有 exit code）
rockcli sandbox <id> exec 'tail -20 /data/logs/user-defined/<job_name>.out'

# 搜索错误
rockcli sandbox <id> exec 'grep -i "error\|exception\|failed\|traceback" /data/logs/user-defined/<job_name>.out | tail -30'

# 如果有 artifact，检查输出
rockcli sandbox <id> exec 'ls -R /data/logs/artifacts/<namespace>/<experiment_id>/<job_name>/ 2>/dev/null'
```

---

## Step 5：深入调试（发现问题时）

### Harbor Job 调试

#### 读取详细日志

```bash
# 1. 如果有 exception.txt，先读它
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/<trial_name>/exception.txt'

# 2. Verifier 输出（测试脚本的实际运行结果）
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/<trial_name>/verifier/test-stdout.txt'
rockcli sandbox <id> exec 'cat /tmp/harbor/jobs/<job_name>/<trial_name>/verifier/test-stderr.txt'

# 3. Trial 主日志（先搜关键词）
rockcli sandbox <id> exec 'grep -i "error\|exception\|failed\|traceback" /tmp/harbor/jobs/<job_name>/<trial_name>/trial.log | tail -50'
```

#### 检查 Docker Container 状态

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

#### 查看 Agent 执行轨迹（按需）

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

### Bash Job 调试

```bash
# 1. 查看完整日志
rockcli sandbox <id> exec 'cat /data/logs/user-defined/<job_name>.out'

# 2. 检查沙箱内执行环境
rockcli sandbox <id> exec 'echo "=== Python ==="; python3 --version 2>/dev/null; echo "=== Node ==="; node --version 2>/dev/null; echo "=== Disk ==="; df -h / 2>/dev/null'

# 3. 如果有 artifact，查看内容
rockcli sandbox <id> exec 'cat /data/logs/artifacts/<namespace>/<experiment_id>/<job_name>/* 2>/dev/null | head -100'
```

---

## Step 6：生成报告（必须输出并保存到本地文件）

**每次分析结束必须：**
1. 在对话中输出结构化报告
2. 将报告保存到本地文件：`/tmp/rock-agent-report-<sandbox_id_短>-<timestamp>.md`

### Harbor Job 报告格式

```markdown
## Harbor Job 报告

**沙箱**: <sandbox_id>
**Job**: <job_name>
**类型**: Harbor Job
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

### 行动建议
1. **立即修复**：...
2. **下次运行前**：...
```

### Bash Job 报告格式

```markdown
## Bash Job 报告

**沙箱**: <sandbox_id>
**Job**: <job_name>
**类型**: Bash Job
**时间**: <started_at> → <finished_at>
**耗时**: <duration>
**退出码**: <exit_code>

### 配置
- Script: <script 内容或 script_path>
- Environment: <environment 配置>
- Timeout: <timeout>

### 执行结果
- 状态: ✅ 成功 / ❌ 失败
- 退出码: <0 或非零>
- 关键输出: <摘要>

### 日志摘要
<关键日志片段，特别是错误信息>

### 问题分析（如有）
- 根本原因：...
- 证据：日志关键行
- 建议：...

### 行动建议
1. ...
```

**状态图标：** ✅ 通过 | ❌ 失败 | 🔄 运行中 | ⚠️ 完成但异常

---

## 常见故障速查

### Harbor Job

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

### Bash Job

| 现象 | 典型原因 |
|------|---------|
| 退出码非零 | 脚本执行失败 |
| 超时退出 | `timeout` 设置过短或脚本挂起 |
| 日志截断 | 沙箱资源不足 (OOM / 磁盘满) |
| 无 artifact 输出 | 脚本未写入预期路径或路径权限问题 |

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

## Harbor Job 批量扫描脚本

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
