---
name: harbor-debug
description: Harbor agent bench 运行排查技能。当 harbor agent 跑 benchmark 出现问题时使用，包括：job 失败、trial 异常、reward 为 0 或空、agent 崩溃、verifier 错误、Docker container 异常等。通过系统性分析产物路径、日志、结果和容器状态，给出结构化诊断报告。关键词触发：harbor run 失败、bench 跑不通、agent 没有得分、trial exception、verifier 报错、container 挂了、reward.txt 为空、debug harbor、排查 bench。
---

# Harbor Debug Skill

当 Harbor 跑 bench 出问题时，别瞎猜——先把证据收全，再做诊断。

## 背景

Harbor 是运行在 ROCK 沙箱中的 Agent Benchmark 评测框架。本技能排查 Harbor 评测运行中的各类问题，产物路径取决于启动方式：`harbor run` 对应 `./jobs/`，ROCK 平台对应 `/data/logs/user-defined/`。

## 工作流程

### Phase 1：定位产物目录

Harbor 的产物存储结构（从 job_dir 往下）：

```
jobs/
└── <job_name>/                    # Job 根目录（JobConfig.jobs_dir / job_name）
    └── <trial_name>/              # Trial 目录（每个 task × attempt 一个）
        ├── config.json            # Trial 配置（agent、task、model 等）
        ├── result.json            # Trial 结果（reward、异常、耗时）
        ├── trial.log              # 完整运行日志
        ├── exception.txt          # 异常信息（若有）
        ├── agent/                 # Agent 运行产物（轨迹、工具调用记录）
        ├── verifier/              # Verifier 产物
        │   ├── test-stdout.txt    # 测试脚本标准输出
        │   ├── test-stderr.txt    # 测试脚本标准错误
        │   ├── reward.txt         # 奖励分数（0~1 的数字）
        │   └── reward.json        # 结构化奖励（若有）
        └── artifacts/             # 从环境中收集的产物
            └── manifest.json      # 产物清单
```

**默认路径：**
- Job 产物根目录：`./jobs/`（相对于运行 `harbor run` 的目录）
- Trial 独立运行：`./trials/`

**定位步骤：**
1. 确认用户运行 harbor 的工作目录（通常是项目根目录）
2. 检查 `./jobs/` 是否存在，列出最近的 job 目录
3. 如果用户提供了 job_name 或 job_dir，直接跳转

```bash
# 列出最近的 job 运行
ls -lt ./jobs/ | head -20

# 查看某个 job 下的所有 trials
ls ./jobs/<job_name>/

# 快速扫描哪些 trial 有异常
ls ./jobs/<job_name>/*/exception.txt 2>/dev/null
```

---

### Phase 2：收集 Trial 结果

对每个相关 trial，读取以下文件：

**必读（先读这几个，5 秒内知道大概情况）：**
```bash
# 1. 结果摘要
cat ./jobs/<job_name>/<trial_name>/result.json

# 2. 异常信息（如果有）
cat ./jobs/<job_name>/<trial_name>/exception.txt

# 3. Reward 分数
cat ./jobs/<job_name>/<trial_name>/verifier/reward.txt
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

---

### Phase 3：分析日志

**按严重程度排序读取：**

```bash
# 1. 如果有 exception.txt，先读它
cat ./jobs/<job_name>/<trial_name>/exception.txt

# 2. Verifier 输出（测试脚本的实际运行结果）
cat ./jobs/<job_name>/<trial_name>/verifier/test-stdout.txt
cat ./jobs/<job_name>/<trial_name>/verifier/test-stderr.txt

# 3. Trial 主日志（可能很长，先搜关键词）
grep -i "error\|exception\|failed\|traceback" \
  ./jobs/<job_name>/<trial_name>/trial.log | tail -50

# 4. 完整 trial.log（按需）
tail -200 ./jobs/<job_name>/<trial_name>/trial.log
```

**Agent 产物（如果有轨迹记录）：**
```bash
ls ./jobs/<job_name>/<trial_name>/agent/
# ATIF 格式的轨迹文件通常是 trajectory.json 或类似
```

---

### Phase 4：检查 Docker Container 状态

**查看 Harbor 相关的 container：**

Harbor Docker container 命名规则：`hb__<environment_name>`（小写）

```bash
# 列出所有 Harbor 相关 container（运行中和已停止的）
docker ps -a | grep "hb__"

# 查看 container 详情（最近退出状态、端口映射）
docker inspect <container_name> | python3 -c "
import json, sys
data = json.load(sys.stdin)[0]
state = data['State']
print(f'Status: {state[\"Status\"]}')
print(f'ExitCode: {state[\"ExitCode\"]}')
print(f'Error: {state[\"Error\"]}')
print(f'OOMKilled: {state[\"OOMKilled\"]}')
print(f'StartedAt: {state[\"StartedAt\"]}')
print(f'FinishedAt: {state[\"FinishedAt\"]}')
"

# 查看 container 最近日志（不依赖文件，直接从 Docker 拉）
docker logs <container_name> --tail 100

# 查看 container 日志中的错误
docker logs <container_name> 2>&1 | grep -i "error\|exception\|killed\|oom" | tail -30

# 如果 container 还在运行，检查资源使用
docker stats <container_name> --no-stream
```

**Docker compose（Harbor 用 compose 管理多容器）：**
```bash
# 查找 Harbor 生成的 compose 文件
find ./jobs/<job_name>/<trial_name> -name "docker-compose*.yaml" 2>/dev/null

# 用 compose 查看服务状态
docker compose -f <compose_file> ps
docker compose -f <compose_file> logs --tail 50
```

---

### Phase 5：生成诊断报告

收集完数据后，输出以下结构的报告：

---

## Harbor Debug 诊断报告

**Job：** `<job_name>`  
**时间：** `<started_at>` → `<finished_at>`  
**分析时间：** `<当前时间>`

### 执行摘要

| 项目 | 状态 |
|------|------|
| Trial 总数 | N |
| 成功（reward > 0）| N |
| 失败（exception）| N |
| 未完成 | N |
| 平均 Reward | 0.xx |

### 问题清单

列出发现的所有问题，按严重程度排序：

**[CRITICAL] 问题标题**
- 影响 trial：`<trial_name>`
- 根本原因：...
- 证据：`exception.txt` 第 N 行 / `trial.log` 关键日志
- 建议：...

**[WARNING] 问题标题**
- ...

### Trial 详情

| Trial | Reward | 状态 | 耗时 | 问题 |
|-------|--------|------|------|------|
| trial_1 | 1.0 | 成功 | 45s | - |
| trial_2 | 0.0 | 异常 | 8s | ImportError: ... |

### 根因分析

按类别归纳：

**环境问题**（Docker/依赖/网络）
- ...

**Agent 问题**（配置/模型/token 超限）
- ...

**Verifier 问题**（测试脚本/奖励计算）
- ...

**Task 问题**（任务定义/instruction 不清）
- ...

### 行动建议

1. **立即修复**：...
2. **下次运行前**：...
3. **长期改进**：...

---

## 常见故障模式速查

### Reward 为 0 但没有异常
- verifier test 运行了但测试没通过
- 查 `verifier/test-stdout.txt` 和 `test-stderr.txt`
- 看 agent 是否真的完成了任务（看 `trial.log` 末尾）

### Exception: TimeoutError
- agent 运行超时
- 看 `config.json` 中的 `timeout_sec`
- 看 `agent_execution.duration_sec` 是否接近 timeout

### Exception: DockerException / Container 相关
- container 启动失败或崩溃
- `docker logs <container_name>` 查看原始日志
- 检查 OOMKilled（内存不足）

### reward.txt 为空或不存在
- verifier 没有运行到写 reward 的步骤
- 可能是 test.sh 崩溃了
- 查 `verifier/test-stderr.txt`

### agent_result 为 null，execution 时间极短
- agent setup 失败（安装脚本报错）
- 查 `trial.log` 中的 setup 阶段日志

### 所有 trial 都失败，同样的 exception
- 环境层面的问题（镜像、依赖、网络）
- 优先看 exception.txt 的 exception_type

## 脚本工具

### 批量扫描 job 下所有 trial 的状态

```python
#!/usr/bin/env python3
# 保存为 scan_job.py，用法：python3 scan_job.py ./jobs/<job_name>
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

使用方式：
```bash
# 快速扫描整个 job
python3 scan_job.py ./jobs/<job_name>

# 或者直接在 shell 里扫描
for d in ./jobs/<job_name>/*/; do
  echo "=== $(basename $d) ==="
  cat "$d/verifier/reward.txt" 2>/dev/null || echo "no reward"
  cat "$d/exception.txt" 2>/dev/null | head -3
done
```
