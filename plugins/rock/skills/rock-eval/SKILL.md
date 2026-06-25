---
name: rock-eval
description: 使用 rockcli（rc）对 AI Agent 做批量回归评估：在数据集上跑分、生成报告、排查与重试失败用例、深度分析失败原因。当用户要跑 benchmark / regression / agent eval、查看 reward 与通过率、对一批任务的评估结果做分析、深度分析失败原因、做 trajectory 分析或 post-mortem 时使用。
---

# Rock Eval — AI Agent 回归评估

本 skill 使用 `rockcli`（别名 `rc`）和 `regression.py` 编排完整的回归评估流程，涵盖：分发任务、监控进度、分析结果、诊断失败和重试。

## 使用场景

- 运行 agent 评估 / benchmark / regression
- 查看评估结果、pass rate、reward 分数
- 排查或重试失败任务
- 涉及 `rc`、`rockcli`、`regression.py`、experiment ID 或结果 JSON 文件

## 快速决策树

```
用户想做什么？
│
├─ 跑新的回归评估 ────────────────────→ Section 1: Run
├─ 查看结果 / 生成报告 ──────────────→ Section 2: Report
├─ 任务卡在 "dispatched" ────────────→ Section 3: Sync（Monitor: Cron 每 3 分钟 sync+判可疑，可疑时调 rock-agent-debug，见 references/team-orchestration.md § Monitor）
├─ 了解任务为什么失败 ────────────────→ Section 4: Diagnose
├─ 重跑失败任务 ──────────────────────→ Section 5: Retry
├─ 深度分析失败原因 ──────────────────→ Section 6: Analyze（→ references/deep-analysis.md）
├─ 在沙箱内执行回归 / 用 zb-a 沙箱长跑 rock bench
│   ───────────────────────────────→ Section 7: Sandbox Run
├─ 手动 rc 命令 ──────────────────────→ 读 references/rockcli-cheatsheet.md
├─ Harbor Job config YAML / agent kwargs → 读 references/harbor-config-manual.md
├─ 全量回归（长跑 + 多失败分诊）
│   → TeamCreate（推荐）: references/team-orchestration-teamcreate.md
│     （TaskList 状态机 + schemas: references/schemas.json）
│   → Legacy v2（单 session）: references/team-orchestration.md（7 角色并行 pipeline）
│   → 不要混用两种模式
├─ 失败后调参 → references/team-orchestration.md § Operator（legacy）
│   或 references/team-orchestration-teamcreate.md § task-11（TeamCreate）
└─ 完整 SOP / 工作流参考 ────────────→ 读 references/sop.md
```

## 核心流程

```
run  ──→  report  ──→  sync（如需）──→  diagnose  ──→  retry
 ^                                                       │
 └───────────────────────────────────────────────────────┘
```

脚本位于本 skill 目录的 `scripts/regression.py`。**通过绝对路径运行，不要复制。** 输出（`results/`、`logs/`、`configs/`）写入调用时的工作目录。

---

## 1. Run — 分发回归任务

```bash
python3 regression.py run \
  --bench <BENCH> \
  --dataset <DATASET> \
  --split <SPLIT> \
  --agent <AGENT> \
  --concurrency <N> \
  --window-size <N>
```

### 必填参数

| 参数 | 说明 |
|-----|---------|
| `--bench` | Bench 模板 — 执行 `rc agent run --help` 查看当前可用值 |
| `--agent` | Agent 名称 — 执行 `rc agent run --help` 查看当前可用值 |
| `--window-size` | **全局并发上限**（滑动窗口，始终保持 N 个任务在执行）。**分发前需与用户确认。** `0` = 无限制 |
| `--concurrency` | `--window-size` 的别名；两者同时指定时取较小值 |

`--dataset` 和 `--split` 为必填，除非指定了 `--tasks`。

### 仅有 bench 名称时解析任务列表

用户只提供 bench 名称时：

1. `rc agent bench getconfig <BENCH> --raw` → 读取 `datasets` 字段（name、registry.split、task_names）
2. `rc datasets <NAME> tasks --split <SPLIT>` → 传给 `regression.py run` 或通过 `--tasks` 指定
3. **兜底**：若 `tasks` 子命令无返回，使用 `--raw` 输出中的 `task_names`

### Agent / bench 取值

**不要硬编码** — 执行 `rc agent run --help` 查看当前支持值。用 `rc agent deps sync benchhub` 刷新 bench 模板。

两个稳定基线：

| Agent | 含义 |
|-------|---------|
| `oracle` | 上界基线 — 提交正确答案；验证评分链路 |
| `nop` | 下界基线 — 什么都不做；验证分发/镜像/集群 |

> ⚠️ **在用真实 agent 跑全量回归之前，询问用户是否先用 `oracle`/`nop` 做冒烟验证**（少量 `--tasks` + 低并发）。流程见 `references/sop.md`。

### Alignment baseline（对齐分数场景，可选）

在 oracle/nop 冒烟后、全量 run 前，**询问用户**是否目标是 reproduce/align 已知分数：

**是**：
1. 获取参考分数（用户提供 / 从 leaderboard/paper 提取）
2. 配置交叉检查：对比 model / image / split / env vars / 采样推理参数（temperature · top_p · thinking · max_tokens · 推理超时）；标出不一致
3. 创建 baseline 文件：`baselines/<benchmark-name>-<identifier>.json`（格式见 `references/data-formats.md` § 对齐基线文件）

**否**：直接进入全量 run。

### 透传参数

**不要假设默认值**，只传用户指定的参数：`--image`、`--cluster`、`--model`、`--ee KEY=VALUE`、`--set path=value`、`--pre`/`--no-pre`、`--namespace`、`--cpus`、`--memory`、`--with-companion`、`--config`、`--async-mode`、`--user-id`、`--base-url`、`--api-key`

> `--model` 可选，省略则使用 ROCKCLI 共享 model。

### 控制参数

| 参数 | 说明 |
|-----|---------|
| `--resume` | 跳过已标记 success 或 error 的任务 |
| `--tasks t1,t2,...` | 仅运行指定任务 |
| `--poll-interval` | 轮询间隔秒数（默认 10） |
| `--poll-timeout` | 单任务最大等待秒数（默认 600） |

### 配置持久化

每次 `run`/`retry` 自动快照配置到 `configs/<experiment-id>.json`。

```bash
# 保存配置模板
python3 regression.py run --bench <BENCH> --agent <AGENT> ... --save-config ./my-template.json

# 从模板运行（CLI 参数覆盖 JSON）
python3 regression.py run --from-config ./my-template.json --concurrency 8
```

| 参数 | 说明 |
|------|----------|
| `--save-config <path>` | 额外将生效配置保存到 `<path>` |
| `--from-config <path>` | 加载为基础配置；CLI 参数覆盖 JSON 中的对应字段 |

JSON 包含完整参数集（bench/dataset/split/agent/所有透传参数/tasks/concurrency/poll），不含 experiment id（每次重新生成）。注意 `--config`（rc 的 JobConfig YAML）是已有的不同参数。

### 输出

- 结果 JSON：`results/<experiment-id>.json`
- 配置快照：`configs/<experiment-id>.json`
- 任务日志：`logs/<experiment-id>/<task-id>.log`

---

## 2. Report — 查看结果

```bash
python3 regression.py report                          # 最新实验，文本格式
python3 regression.py report <EXPERIMENT_ID>          # 指定实验
python3 regression.py report --format html --open     # HTML 仪表盘
python3 regression.py report --format json            # JSON 供脚本使用
```

HTML 报告包含：KPI 卡片、环形图、reward 直方图、exception 分组表、可交互任务表。

---

## 3. Sync — 刷新过期状态

```bash
python3 regression.py sync [EXPERIMENT_ID]
python3 regression.py sync --dry-run    # 预览，不写入
python3 regression.py sync --force      # 重新同步所有任务
```

运行被中断后，生成报告前务必先执行 sync。

### Monitor 巡检机制（长跑时）

见 `references/team-orchestration.md` § Monitor。巡检角色用 **Cron 每 3 分钟 session-only** 定时：

1. `sync` → 2. `report --format json` → 3. 维护 `logs/<EXP_ID>/monitor-state.json` → 4. 按 4 条判据判"假执行"：dispatched 连续 ≥3 次不降 / error 堆积 / pass rate 远低于预期 / 单 task 超推理超时 1.5 倍
5. **可疑时才**调 `rock-agent-debug`（experiment_id + job_name）确认；正常则不调
6. run 结束后用 CronDelete 清理 Cron

> ⚠️ **Cron 为 session-only**，会话关闭则停止。跨会话长跑需用 `durable: true`。

---

## 4. Diagnose — 失败分诊

```bash
# 概览
python3 regression.py diagnose [EXPERIMENT_ID]
python3 regression.py diagnose --status error
python3 regression.py diagnose --exception RuntimeError

# 单任务深入
python3 regression.py diagnose --task <TASK_ID>
python3 regression.py diagnose --task <TASK_ID> --remote       # + 服务端日志
python3 regression.py diagnose --task <TASK_ID> --trajectory   # + 执行轨迹
python3 regression.py diagnose --task <TASK_ID> --artifacts    # + 输出文件
python3 regression.py diagnose --task <TASK_ID> --tail 50      # 最后 50 行
```

---

## 5. Retry — 重跑失败任务

```bash
python3 regression.py retry [EXPERIMENT_ID] \
  --bench <BENCH> --agent <AGENT> --concurrency <N> --window-size <N>

python3 regression.py retry --filter error ...
python3 regression.py retry --filter error --exception-type RewardFileNotFoundError ...
python3 regression.py retry --tasks t1,t2,t3 ...
```

| | `run --resume` | `retry` |
|---|---|---|
| 跳过 | success + error | 仅 success |
| Experiment ID | 复用原 ID | 新 ID（带 `retry_of` 引用） |
| 过滤 | 无 | 按 status、exception type、手动列表 |

`retry` 支持与 `run` 相同的 `--save-config`/`--from-config` 配置持久化（JSON 为基础，CLI 覆盖）。

---

## Section 6: Analyze — 深度失败分析

对已完成实验做系统性 trajectory 分析，逐任务定位失败根因。**完整指南**读取 `references/deep-analysis.md`。

| Phase | 做什么 | 输出 |
|-------|--------|------|
| 1. 实验概览 | 用 `live-score.py` 获取全量数据 | `overview.json` |
| 2. 并行深度分析 | 每批 5-8 个子 agent 分析失败 job 的 trajectory | 每 task 一个 `.md` 分析文件 |
| 3. 模式聚合 | 汇总失败分类分布 + 改进建议 | `SUMMARY.md` |

```bash
# Phase 1
python3 scripts/live-score.py -e <EXP_ID> [--pre] --text
# 或
python3 scripts/fetch-overview.py <EXP_ID> [--pre] --output /tmp/bench-analysis-<EXP_ID>/overview.json
```

Phase 2/3 见 `references/deep-analysis.md`。**失败分类体系**见 `references/failure-taxonomy.md`（8 种分类 + 边界判断指南）。

---

## Section 7: Sandbox Run — 沙箱内执行回归

适用于需要内网环境访问或长时间隔离执行的场景。

**架构**：先起一个"控制沙箱"安装 rockcli / regression.py，再从沙箱内分发 `rc agent run`。
控制沙箱所在集群和 agent job 运行集群是两层配置，必须分开确认：

| 层级 | 参数位置 | 说明 |
|------|----------|------|
| 控制沙箱集群 | `rc --cluster <sandbox-cluster> sandbox start ...` | 用来安装 rockcli、保存脚本、后台跑回归控制进程 |
| agent job 集群 | `regression.py run --cluster <job-cluster>` | 透传给沙箱内每个 `rc agent run`，决定评测 job 跑在哪个 ROCK 集群 |

### 推荐集群组合

| 场景 | 控制沙箱 | agent job |
|------|----------|-----------|
| **zb-a 回归 rock bench** | `zb-a` | 按 bench/镜像要求单独确认，常见为 `vpc-zb-a` 或用户指定集群 |
| sg-a 兼容路径 | `sg-a` | `vpc-sg-a` |

> ⚠️ 用户明确说"用 `zb-a` 沙箱"时，控制沙箱必须是 `zb-a`，不要写成 `vpc-zb-a`。
> `--cluster` 是 `rc` 全局选项，起控制沙箱时必须放在 `rc` 后、`sandbox` 前：`rc --cluster zb-a sandbox start ...`。
> agent job 的 `--cluster` 在 `regression.py run` / 配置 JSON 中设置，不能用控制沙箱集群替代。

**执行前向用户确认**：工号（`user_id`）、`ROCK_TOKEN`、`ANTHROPIC_API_KEY`、其他 env var、rockcli 版本（正式/beta）。

### Step 1 — 启动沙箱

```bash
# zb-a 控制沙箱；auto-clear 5 天适合长跑回归，按用户要求调整
rc --cluster zb-a sandbox start \
  --auto-clear 432000 \
  --wait-for-alive \
  --memory 64g \
  --cpus 16
```

`sandbox start` 仅支持：`--image`、`--memory`、`--cpus`、`--timeout`、`--auto-clear`、`--wait-for-alive`。输出中包含 `SANDBOX_ID`（如 `sb-xxxxxxxx`）。

### Step 2 — 安装 rockcli

```bash
rc sandbox <SANDBOX_ID> exec 'bash -c "$(curl -fsSL http://xrl.alibaba-inc.com/install.sh)"'
# beta 版
rc sandbox <SANDBOX_ID> exec 'bash -c "$(curl -fsSL http://xrl.alibaba-inc.com/install_beta.sh)"'
rc sandbox <SANDBOX_ID> exec 'export PATH=/root/.local/bin:/root/.nvm/versions/node/v22.23.1/bin:$PATH && rc --version'
```

如果 `rc` / `rockcli` 不在 PATH，优先在启动脚本里显式设置：

```bash
export PATH=/root/.local/bin:/root/.nvm/versions/node/v22.23.1/bin:/usr/local/bin:/usr/bin:/bin:$PATH
```

### Step 3 — 注入凭据

> ⚠️ 沙箱不支持 `-e` 传入 env var，必须通过 `exec` 写入 `~/.bashrc`。

```bash
rc sandbox <SANDBOX_ID> exec 'echo "export ROCK_TOKEN=<TOKEN>" >> ~/.bashrc'
rc sandbox <SANDBOX_ID> exec 'echo "export ANTHROPIC_API_KEY=<KEY>" >> ~/.bashrc'
# 验证
rc sandbox <SANDBOX_ID> exec 'source ~/.bashrc && rc agent bench list --pre'
```

### Step 4 — 确认回归配置

在本机按 Section 1 确认参数并生成 `--save-config ./my-config.json`。对 rock bench 尤其要确认：

- bench / dataset / split / tasks
- agent / model / image
- agent job 集群：例如 `--cluster vpc-zb-a`，或用户明确指定的其他集群
- 资源规格：`--cpus` / `--memory`
- `--pre` / `--no-pre`
- window size / concurrency

### Step 5 — 创建目录并上传文件

```bash
rc sandbox <SANDBOX_ID> exec 'mkdir -p /workspace/scripts /workspace/results /workspace/logs /workspace/configs'
rc sandbox <SANDBOX_ID> upload --dir <local-scripts-dir> --target-path /workspace/scripts --recursive
rc sandbox <SANDBOX_ID> upload --file ./my-config.json --target-path /workspace/my-config.json
```

### Step 6 — 后台启动回归

> ⚠️ **必须用 `setsid` 或 `nohup ... &`**，否则 exec 超时断连后进程可能被杀。Linux 沙箱内优先用 `setsid`；本机 macOS 通常没有 `setsid`，不要在本机验证这条命令。

```bash
rc sandbox <SANDBOX_ID> exec 'bash -lc "source ~/.bashrc; export PATH=/root/.local/bin:/root/.nvm/versions/node/v22.23.1/bin:/usr/local/bin:/usr/bin:/bin:\$PATH; cd /workspace; setsid python3 scripts/regression.py run --from-config /workspace/my-config.json --cluster <JOB_CLUSTER> --window-size 10 > /workspace/logs/regression.out 2>&1 < /dev/null &"'
```

若沙箱内没有 `setsid`，回退：

```bash
rc sandbox <SANDBOX_ID> exec 'bash -lc "source ~/.bashrc; cd /workspace; nohup python3 scripts/regression.py run --from-config /workspace/my-config.json --cluster <JOB_CLUSTER> --window-size 10 > /workspace/logs/regression.out 2>&1 < /dev/null &"'
```

### Step 7 — 监控进度

```bash
rc sandbox <SANDBOX_ID> exec 'tail -50 /workspace/logs/regression.out'
rc sandbox <SANDBOX_ID> log search --log-file command.log -m 30
rc sandbox <SANDBOX_ID> exec 'pgrep -af "regression.py run|rc agent run|rockcli agent run"'
```

也要直接查平台实验状态：

```bash
rc agent view --pre -e <EXP_ID> -o json --limit 100
```

### Step 8 — 取回结果

```bash
rc sandbox <SANDBOX_ID> exec 'ls /workspace/results/'
rc sandbox <SANDBOX_ID> download --file /workspace/results/<EXP_ID>.json
rc sandbox <SANDBOX_ID> download --file /workspace/configs/<EXP_ID>.json
python3 regression.py report /path/to/<EXP_ID>.json
```

### Step 9 — 停止沙箱

```bash
rc sandbox <SANDBOX_ID> stop
```

> 务必先完成 Step 8，stop 后文件不可访问。

如需终止已经分发的实验，先杀控制沙箱内后台进程，再停止实验下 RUNNING/PENDING 沙箱：

```bash
rc sandbox <SANDBOX_ID> exec 'pkill -f "regression.py run|rc agent run|rockcli agent run" || true'
rc expr <EXP_ID> sandboxes stop --dry-run
rc expr <EXP_ID> sandboxes stop -y --concurrency 10 --fetch-concurrency 5
```

### 常见陷阱

| 陷阱 | 说明 |
|------|------|
| 把 `zb-a` 写成 `vpc-zb-a` | 用户要求 zb-a 控制沙箱时，`sandbox start` 用 `rc --cluster zb-a ...` |
| 混淆两层 cluster | 控制沙箱 cluster 和 agent job cluster 是两件事，分别确认 |
| 忘记 agent job `--cluster` | 沙箱内 `regression.py run` 仍需带用户确认的 job cluster |
| `--cluster` 位置错误 | 起控制沙箱时是 `rc --cluster zb-a sandbox ...`，不能放子命令后 |
| 不加 `setsid` / `nohup &` | exec 断连后进程终止 |
| 凭据未 `source ~/.bashrc` | 每次 exec 是新 shell，必须 source |
| rockcli 不在 PATH | 沙箱内显式 export `/root/.local/bin` 和 nvm node bin |
| stop 前未下载结果 | 沙箱停止后文件不可访问 |
| `sandbox start` 参数传错 | `--env`/`-e` 不合法，只允许上方列出的 6 个参数 |
| pictor-permissions 间歇性 500 | 出口 IP 访问鉴权不稳定，可重试 |

---

## Experiment ID 解析规则

1. **省略** — 使用 `results/` 中最近修改的文件
2. **实验 ID** — 匹配 `results/{id}.json`，再前缀匹配 `results/{id}*.json`
3. **文件路径** — 直接使用

---

## 附带资源

| 路径 | 何时读取 |
|------|-------------|
| `references/sop.md` | 完整 SOP、典型工作流、详细参数参考 |
| `references/rockcli-cheatsheet.md` | 原始 `rc` 命令（手动查询、数据集浏览、沙箱管理） |
| `references/harbor-config-manual.md` | Harbor Job `config.yaml`、JobConfig 字段、timeout/kwargs |
| `references/data-formats.md` | 结果 JSON 结构、任务字段、exception 类型、解析方式 |
| `references/team-orchestration.md` | 全量回归 — legacy v2 prompt 驱动（单 session，7 角色） |
| `references/team-orchestration-teamcreate.md` | 全量回归 — TeamCreate 模式（推荐，跨 session 恢复） |
| `references/schemas.json` | TeamCreate 结构化输出 schemas（SmokeOutput、ConfigConfirmOutput、SmokeDecisionOutput） |
| `references/deep-analysis.md` | 深度失败分析完整指南（三阶段工作流），Section 6 触发时读取 |
| `references/failure-taxonomy.md` | 8 种失败分类定义、识别方法和边界判断指南 |

---

## 常见场景

### 跑新的 benchmark

1. 确认：bench、dataset、split、agent、concurrency 及透传参数（image/cluster/model 等）
2. **询问是否先用 `oracle`/`nop` 冒烟验证**（见 Section 1）
3. `regression.py run`
4. 完成后生成 HTML 报告

### 运行被中断

1. `regression.py sync` → 2. `regression.py report` → 3. `regression.py run --resume`

### 任务为什么失败

1. `regression.py diagnose` 概览 → 2. 选 top exception group 代表 task → 3. `regression.py diagnose --task <ID> --remote --trajectory` → 4. 根据根因建议修复或 retry

### 只重跑 Docker 失败的任务

1. `regression.py diagnose --exception RuntimeError` 确认集合
2. `regression.py retry --filter error --exception-type RuntimeError ...`
3. `regression.py report` 查看新实验

### 查看可用的 dataset/agent/bench

读 `references/rockcli-cheatsheet.md`，使用 `rc datasets`、`rc agent bench list` 等。

### 对齐/复现已发布分数

1. 确认 bench/dataset/split，获取参考分数来源
2. 提取 per-task reward（或 aggregate pass rate）
3. 配置交叉检查：对比 model / image / split / env vars / 采样推理参数（temperature · top_p · thinking · max_tokens · 推理超时）
4. 创建 `baselines/<name>.json`（格式见 `references/data-formats.md` § 对齐基线文件）
5. Oracle/nop 冒烟 → `regression.py run` → 报告 + alignment 对比（actual vs expected reward、配置 drift、top gap tasks）
6. 根据结论决定：调参 retry / 接受差异 / 报告给用户
