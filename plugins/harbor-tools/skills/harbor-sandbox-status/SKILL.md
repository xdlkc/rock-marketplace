---
name: harbor-sandbox-status
description: 分析运行在 ROCK 沙箱（sandbox）中的 Harbor 任务执行状态。当用户提供沙箱 ID 并询问 harbor 任务的状态、进度、日志、reward、agent 执行情况时使用。支持多种 agent（claude-code、terminus-2、openhands、swe-agent 等）和 bench（terminal-bench、swe-bench-verified 等）。触发词：沙箱里跑的 harbor、查一下 sandbox 里的 harbor job、看看 trial 状态、bench 跑到哪了、查 reward、看 agent 日志、查沙箱 XXX 的 harbor 任务。
---

# Harbor Sandbox Status Skill

通过 `rockcli` 查询运行在 ROCK 沙箱中的 Harbor 任务执行状态，最终产出一份落盘的详细报告。

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

```bash
# 列出 trials
rockcli sandbox <id> exec 'ls /tmp/harbor/jobs/<job_name>/ 2>/dev/null || ls /data/logs/user-defined/jobs/<job_name>/ 2>/dev/null'

# 批量查看所有 trial 状态（快速）
rockcli sandbox <id> exec 'for t in /tmp/harbor/jobs/<job_name>/*/; do echo "=== $(basename $t) ==="; cat "$t/result.json" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(\"reward:\", d.get(\"verifier_result\"), \"exception:\", bool(d.get(\"exception_info\")))" 2>/dev/null || cat "$t/trial.log" 2>/dev/null | head -3; done'
```

**判断 Trial 当前阶段（从 result.json）：**
- `environment_setup` 有值，`agent_setup` 为 null → 环境启动中
- `agent_setup` 有值，`agent_execution` 为 null → Agent 安装中
- `agent_execution` 有值，`verifier` 为 null → Agent 执行中
- `verifier` 有值，`finished_at` 为 null → Verifier 运行中
- `finished_at` 有值 → 已完成

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
└── agent/trajectory.json    # Agent 执行轨迹（ATIF 格式，若有）
```

---

## Step 5：查看 Agent 执行轨迹（按需）

用户想了解 agent 做了什么时才查。

```bash
# trajectory.json（ATIF 格式，swe-agent/terminus 等支持）
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

# Docker 容器日志（容器还在时）
rockcli sandbox <id> exec 'docker ps -a | grep <trial_id_lower>'
rockcli sandbox <id> exec 'docker logs <container_name> 2>&1 | tail -50'
```

---

## Step 6：生成状态报告（必须输出并保存到本地文件）

**每次分析结束必须：**
1. 在对话中输出结构化报告
2. 将报告保存到本地文件：`/tmp/harbor-status-<sandbox_id_短>-<timestamp>.md`

报告格式：

```markdown
## Harbor 任务状态报告

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
| Trial | 状态 | Reward | 耗时 | 失败阶段 |
|-------|------|--------|------|---------|
| <name> | ✅/❌/🔄/⚠️ | <reward> | <duration> | <phase 或 ->> |

### 执行时间线
- `<HH:MM>` 环境启动完成（耗时 Xs）
- `<HH:MM>` Agent 安装完成（耗时 Xs）
- `<HH:MM>` Agent 开始执行
- `<HH:MM>` Agent 执行完成（耗时 Xs）
- `<HH:MM>` Verifier 完成，reward=<N>

### Agent 执行摘要（如有 trajectory）
- 共执行 <N> 步
- 主要操作：<简短描述，如"查看文件 → 修改代码 → 运行测试">

### 失败分析（如有）
- **失败阶段**: <env_setup / agent_setup / agent_exec / verifier>
- **异常类型**: <exception_type>
- **错误摘要**: <前 300 字>
- **根因推断**: <简短分析>
```

**状态图标：** ✅ 通过（reward>0）| ❌ 失败 | 🔄 运行中 | ⚠️ 完成但异常

保存命令示例：
```bash
# 保存报告到本地
cat > /tmp/harbor-status-<sandbox_short>-$(date +%Y%m%d_%H%M%S).md << 'EOF'
<报告内容>
EOF
echo "报告已保存至 /tmp/harbor-status-..."
```

---

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

## 常见失败模式

| 现象 | 失败阶段 | 典型原因 |
|------|---------|---------|
| "Docker compose command failed" / "no such host" | env_setup | 镜像拉取 DNS 失败 |
| `agent/setup/return-code.txt` = 100 | agent_setup | Agent 安装脚本失败 |
| `AgentTimeoutError` | agent_execution | Agent 超时 |
| reward=0，无异常 | verifier | Agent 完成但未解决问题 |
| `RewardFileNotFoundError` | verifier | reward.txt 不存在 |
| `no running event loop` | cleanup | Agent 超时后清理阶段崩溃（非主要失败原因） |
