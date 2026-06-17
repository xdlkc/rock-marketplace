# 数据格式参考

regression.py 产生和消费的数据文件格式说明。

---

## 结果 JSON (`results/<experiment-id>.json`)

regression.py 所有子命令共享的核心数据文件。

```jsonc
{
  // ─── 实验元信息 ───
  "experiment_id": "aone-bench-java100-20260613_002258",
  "bench": "aone-bench",
  "dataset": "alibaba/aone-bench-java100",
  "split": "delivery_0609-cn",
  "image": "rock-registry-vpc...",          // Docker 镜像，可选
  "cluster": "vpc-zb-a",                    // 集群标识，可选
  "concurrency": 30,
  "started_at": "2026-06-12T16:22:58+00:00",
  "finished_at": "2026-06-12T21:10:25+00:00",  // null = 进行中
  "retry_of": "aone-bench-java100-20260612_142317",  // 仅 retry 产生的实验有此字段

  // ─── 汇总统计 ───
  "summary": {
    "total": 187,
    "dispatched": 14,       // 已派发但未完成
    "success": 95,
    "error": 78,
    "pending": 0            // total - dispatched - success - error
  },

  // ─── 任务详情 ───
  "tasks": {
    "<task_id>": {
      "task_id": "codereview-20714246",
      "status": "success",               // pending | dispatched | success | error
      "sandbox_id": "27b9c2d7...",       // 沙箱 ID
      "job_name": "job-fc3e5efa",        // Job 名称，用于 rc agent view/fs
      "dispatched_at": "2026-06-12T16:22:58+00:00",
      "finished_at": "2026-06-12T16:51:20+00:00",
      "reward": 1,                       // 0-1 浮点数，null = 未评分
      "n_trials": 1,
      "n_completed": 1,
      "n_errors": 0,
      "exception_type": null,            // 异常类型，如 "RuntimeError"
      "exception_message": null,         // 异常消息全文
      "agent_name": "mini-swe-agent",
      "duration_ms": 1584081             // 执行耗时（毫秒），null = 未知
    }
  }
}
```

### 任务状态流转

```
pending → dispatched → success
                    → error
```

- `pending`: 在任务列表中但尚未派发
- `dispatched`: 已发送到服务端，等待完成
- `success`: 执行完成（reward 可能为 0）
- `error`: 执行失败（有 exception 信息）

### Error 任务示例

```json
{
  "task_id": "codereview-21416490",
  "status": "error",
  "sandbox_id": "9572cf73...",
  "job_name": "job-7966a226",
  "dispatched_at": "2026-06-12T16:22:58+00:00",
  "finished_at": "2026-06-12T17:18:25+00:00",
  "reward": 0,
  "n_trials": 1,
  "n_completed": 1,
  "n_errors": 1,
  "exception_type": "AgentTimeoutError",
  "exception_message": "Agent execution timed out after 3000.0 seconds",
  "agent_name": "mini-swe-agent",
  "duration_ms": 3242873
}
```

### 常见 exception_type

| 类型 | 说明 |
|------|------|
| `RuntimeError` | Docker compose 启动失败、沙箱异常等 |
| `AgentTimeoutError` | Agent 执行超时 |
| `RewardFileNotFoundError` | 评分文件不存在（verifier 问题） |
| `null` / 空 | dispatch 阶段失败，无 job 产生 |

---

## HTML 报告 (`results/<experiment-id>.html`)

自包含单文件，通过 `regression.py report --format html` 生成。

### 报告数据结构

HTML 内部嵌入的 JavaScript 数据对象 `D`：

```jsonc
{
  // 元信息
  "experiment_id": "...",
  "bench": "...",
  "dataset": "...",
  "split": "...",
  "agent": "...",
  "model": "(默认)",
  "cluster": "(默认)",
  "image": "(默认)",
  "started_at": "2026-06-12T16:22:58",
  "finished_at": "2026-06-12T21:10:25",
  "duration_str": "4h 47m",

  // 状态汇总
  "summary": { "total": 187, "success": 95, "error": 78, "dispatched": 14, "pending": 0 },

  // Reward 统计
  "reward_stats": {
    "count": 95, "mean": 0.5263, "min": 0, "max": 1,
    "median": 1.0, "p25": 0.0, "p75": 1.0, "std": 0.502
  },
  "reward_bins": [35, 0, 0, 0, 0, 0, 0, 0, 0, 60],  // 10 个 bin，[0,0.1) 到 [0.9,1.0]

  // 耗时统计（单位: 毫秒）
  "duration_stats": {
    "count": 95, "mean": 1584081, "min": 514000, "max": 3242873,
    "median": 1580000, "p25": 1247000, "p75": 1845000
  },

  // 异常分类（按 exception_type 分组）
  "exceptions": { "RuntimeError": 63, "AgentTimeoutError": 12, "RewardFileNotFoundError": 3 },

  // 去重后的异常消息 TOP 10
  "error_messages": [
    { "msg": "Docker compose command failed ...", "count": 96, "sample": "codereview-20714246" }
  ],

  // 任务列表（供交互表格使用）
  "tasks": [
    {
      "task_id": "codereview-20714246",
      "status": "success",
      "reward": 1,
      "duration_ms": 1584081,
      "exception_type": "",
      "sandbox_id": "27b9c2d7...",
      "job_name": "job-fc3e5efa",
      "agent_name": "mini-swe-agent"
    }
  ]
}
```

### HTML 报告组件

| 组件 | 技术实现 | 说明 |
|------|----------|------|
| KPI 卡片 | CSS Grid + 动画 | 4 张：PASS RATE / AVG REWARD / MEDIAN REWARD / AVG DURATION |
| 环形图 | CSS `conic-gradient` | 按 success/error/dispatched/pending 分色 |
| Reward 直方图 | CSS 竖条 + JS | 只展示有数据的 bin |
| 异常类型表 | HTML table | 按 exception_type 分组计数 + 占比 + 横条 |
| 去重消息表 | HTML table | 归一化后的异常消息 TOP 10 + 示例任务 |
| 任务表格 | Vanilla JS | 搜索、按状态筛选（全部/success/error/dispatched/pending）、列排序 |

---

## 任务日志 (`logs/<experiment-id>/<task-id>.log`)

每个任务的 `rc agent run` 标准输出。包含：

```
sandbox_id=27b9c2d7f4bc479cbe25c9abbf4874d7
job_name=job-fc3e5efa
... rockcli 执行日志 ...
```

关键提取模式：

| 字段 | 正则 |
|------|------|
| `sandbox_id` | `sandbox_id=([a-f0-9]+)` |
| `job_name` | `job_name=([a-zA-Z0-9_-]+)` |
| 错误信息 | 匹配含 `error\|rate limit\|quota` 的行 |

---

## JSON 报告 (`report --format json` 输出)

与 HTML 报告内部 `D` 对象结构相同，直接输出到 stdout。可用于：

```bash
# 提取 pass rate
python3 regression.py report --format json | python3 -c "
import json, sys
d = json.load(sys.stdin)
s = d['summary']
print(f\"Pass rate: {s['success']/s['total']*100:.1f}%\")
"

# 提取所有失败任务 ID
python3 regression.py report --format json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('\n'.join(t['task_id'] for t in d['tasks'] if t['status']=='error'))"
```

---

## 对齐基线文件 (`baselines/<benchmark-name>-<identifier>.json`)

手动创建（由 agent 根据用户提供的参考分数或 leaderboard 数据整理），用于「对齐分数」
场景。Diagnostician 对比实际结果与此文件来定位 score gap。

文件存放在用户工作目录下的 `baselines/` 子目录（与 `results/`/`logs/`/`configs/` 同级）。

```jsonc
{
  // ─── 来源信息 ───
  "meta": {
    "created_at": "2026-06-17T10:00:00+08:00",
    "source": "leaderboard",           // leaderboard | paper | user-provided | internal-history
    "source_url": "https://...",        // 来源 URL（可选）
    "source_description": "Official leaderboard as of 2026-06-15",
    "notes": ""                         // 自由备注
  },

  // ─── 参考配置（官方/paper 使用的配置）───
  "reference_config": {
    "bench": "harborframework/java100",
    "dataset": "aone-bench/java100",
    "split": "test",
    "agent": "claude-code",
    "model": "claude-sonnet-4-20250514",
    "image": "rock-registry-vpc...:33180a83",
    "cluster": "",
    "ee": [],
    "set": []
  },

  // ─── 汇总预期 ───
  "summary": {
    "total_tasks": 187,
    "expected_pass_rate": 0.62,          // 0-1
    "expected_avg_reward": 0.58          // 0-1（可选）
  },

  // ─── 逐 task 预期 reward ───
  "tasks": {
    "<task_id>": {
      "expected_reward": 1.0,            // 0-1，null = 未知
      "notes": ""                        // 可选备注（如 "known flaky"）
    }
  }
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `meta.source` | 是 | 来源类型：`leaderboard` / `paper` / `user-provided` / `internal-history` |
| `meta.source_url` | 否 | 参考来源 URL |
| `meta.source_description` | 否 | 来源描述（如"官方 leaderboard 截至 2026-06-15"） |
| `reference_config` | 是 | 官方/参考使用的完整配置（用于 config drift 对比） |
| `reference_config.bench` | 是 | 与实际 run 的 bench 必须匹配 |
| `reference_config.model` | 否 | 空表示未知/未公开 |
| `summary.total_tasks` | 是 | 参考结果涵盖的任务总数 |
| `summary.expected_pass_rate` | 是 | 参考 pass rate（0-1 浮点数） |
| `summary.expected_avg_reward` | 否 | 参考平均 reward |
| `tasks` | 是 | per-task 预期，至少包含 summary 对应的任务集 |
| `tasks.<id>.expected_reward` | 是 | `null` 表示该 task 无参考数据 |
| `tasks.<id>.notes` | 否 | 可选备注（如 "known flaky", "partial credit expected"） |

### 命名约定

文件名格式：`<benchmark-name>-<identifier>.json`

示例：
- `java100-claude-code-leaderboard-2026Q2.json`
- `swe-bench-lite-paper-v1.json`
- `codereview-user-provided.json`

### Diagnostician 使用方式

Diagnostician 在 alignment 模式下：
1. 读取 `baselines/<file>.json` 的 `tasks` 和 `reference_config`
2. 读取 `results/<experiment-id>.json` 的 `tasks`
3. 读取 `configs/<experiment-id>.json`（实际运行配置）
4. 逐 task 对比 `actual_reward` vs `expected_reward`（跳过 `expected_reward: null` 的 task）
5. 对比 `reference_config` vs 实际 config，标出 drift 字段
6. 报告：配置差异 / 分数对齐度 / gap 分布 / top gap tasks / 根因假设 / 建议
