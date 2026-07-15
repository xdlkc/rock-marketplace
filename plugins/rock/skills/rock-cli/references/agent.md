# agent 命令详细参数

AI Agent 评估任务管理，通过 Python rock-sdk 执行评估任务。需要 Python >= 3.11。

## 目录

- [run - 运行评估任务](#run)
- [view - 查看 Job/Task/Trial 信息](#view)
- [fs - 文件操作](#fs)
- [deps - 依赖管理](#deps)

---

## run

支持两种运行模式：Config 模式（从本地 YAML）和 Bench 模式（从 benchhub 模板）。

```bash
# Config 模式
rockcli agent run --config <config.yaml> [选项]

# Bench 模式
rockcli agent run --bench <name> --task <name> [选项]
```

### 核心参数

| 参数 | 说明 |
|------|------|
| `--config <path>` | JobConfig YAML 配置文件路径（Config 模式必需） |
| `--bench <name>` | Bench 名称（Bench 模式必需，来自 benchhub 模板） |
| `--dataset <name>` | 数据集名称（映射到 `datasets.0.name`） |
| `--split <name>` | 数据集 split/version 名称（映射到 `datasets.0.registry.split`） |
| `--task <name>` | 单任务名称（与 `--tasks`/`--all`/`--resume` 互斥） |
| `--tasks <names...>` | 指定多个任务，由一个底层 ROCK 命令统一执行 |
| `--all` | 显式运行配置中 dataset split 的全部任务 |
| `--resume <run-id>` | 恢复指定 ROCK run（与 task/tasks/all/dataset/split/limit 互斥） |
| `--agent <name>` | Agent 名称（映射到 `agents.0.name`） |
| `--model <name>` | 模型名称（映射到 `agents.0.model_name`） |
| `--namespace, -n <name>` | ROCK 项目空间（默认从 `ROCK_NAMESPACE` / `~/.rock/settings.json` 读取） |

### 执行控制

| 参数 | 说明 |
|------|------|
| `--concurrency <N>` | 多任务/全量任务并发数，默认 1，上限 100 |
| `--limit <N>` | 限制多任务/全量任务数量 |
| `--mode <type>` | `local`（默认）或 `remote`（在 launcher 沙箱中运行） |
| `--remote-cluster <id>` | remote launcher 集群覆盖 |
| `--metadata <type>` | ROCK 元数据后端：`none`（默认）、`local`、`oss` |
| `--metadata-dir <path>` | local 元数据目录（默认 `~/.rock/jobs`） |
| `--pre` | 使用预发环境 |
| `--async` | 异步模式：提取 sandbox_id 后退出 |
| `--quiet` | 后台执行，日志持久化到文件 |
| `--dry-run` | 只生成并展示最终配置，不执行 |
| `--with <name>` | 启用陪跑助手（当前支持 `claude-code`） |
| `--ee <KEY=VALUE>` | 沙箱环境变量，可多次指定 |
| `--set <path=value>` | YAML 字段覆盖，数组用 `.数字` 表示下标 |
| `--auto-clear <sec>` | 自动清理时间（秒） |

### 使用示例

```bash
# Config 模式：从本地 YAML 文件运行
rockcli agent run --config job.yaml

# 覆盖 YAML 中的任务和资源字段
rockcli agent run --config job.yaml --task crack-7z-hash --set environment.cpus=8

# Bench 模式：从 benchhub 模板运行（--task 必传）
rockcli agent run --bench aone-bench --task codereview-20789198

# Bench 模式：指定 Agent 和 Model
rockcli agent run --bench aone-bench --task codereview-20789198 --agent claude-code --model claude-sonnet-4-6

# 多任务并发
rockcli agent run --config job.yaml --tasks task-1 task-2 --concurrency 2

# 全量任务（必须显式传 --all）
rockcli agent run --config job.yaml --all --concurrency 2 --limit 10

# 全量 + 元数据（支持断点重跑）
rockcli agent run --config job.yaml --all --metadata local --metadata-dir /tmp/rock-meta

# 断点重跑
rockcli agent run --config job.yaml --resume 20260710T130922-f16c39a9 --metadata local

# 远程执行（在 launcher 沙箱中）
rockcli agent run --config job.yaml --all --mode remote --remote-cluster vpc-sg-a

# 远程断点重跑 + OSS 元数据
rockcli agent run --config job.yaml --resume 20260710T130922-f16c39a9 --metadata oss --pre --mode remote

# 异步模式（提交后立即返回 sandbox_id）
rockcli agent run --config job.yaml --async

# Claude Code 陪跑
rockcli agent run --bench aone-bench --task codereview-20789198 --with claude-code

# 注入沙箱环境变量
rockcli agent run --config job.yaml --ee API_KEY=sk-xxx --ee DEBUG=1
```

### 行为说明

- `--task`、`--tasks`、`--all`、`--resume` 互斥
- Config YAML 含多个 `task_names` 时无需再传 `--tasks`
- 全量任务不会隐式推断，必须显式传 `--all`
- `--metadata local` 默认使用 `~/.rock/jobs`，只适合当前机器；`oss` 适合跨机器
- resume 必须选择与原 run 相同的 metadata 后端
- `--mode remote` 在 launcher 沙箱中执行，当前不支持 `--quiet`/`--async`/`--with`
- Bash Job（配置含 `script`/`script_path`）会把任务选择显式转发给底层 ROCK
- 沙箱参数优先级：命令参数/`--set` > config.yaml > `ROCK_*` 环境变量 > 内置默认值
- `-vvv` 会在执行前打印 shell-safe 的最终 ROCK 命令

---

## view

查看 Agent jobs, tasks, trials 信息。通过 `-e` 指定实验 ID，逐级钻取。

```bash
rockcli agent view [选项]
```

| 参数 | 说明 |
|------|------|
| `-E, --experiments` | 列举当前 namespace 下的所有实验 |
| `-e, --experiment <id>` | 实验 ID（覆盖配置文件） |
| `-n, --namespace <name>` | 命名空间（覆盖配置文件） |
| `-j, --job <name>` | Job 名称 |
| `-t, --task <name>` | Task 名称（需配合 `--job`） |
| `-T, --trial <name>` | Trial 名称（需配合 `--job` 和 `--task`） |
| `--trajectory` | 展开 trial 的完整轨迹（需配合 `--job`） |
| `--pre` | 使用预发环境 |
| `-o, --output <format>` | 输出格式：table, json, simple（默认 table） |
| `--limit <num>` | Jobs 列表每页返回条数（默认 20） |
| `--offset <num>` | Jobs 列表跳过前 N 条（默认 0） |
| `--q <text>` | 全文搜索（experiments / jobs / tasks） |
| `--agent <name>` | Agent 名过滤（可重复） |
| `--provider <name>` | Provider 名过滤（可重复） |
| `--model <name>` | Model 名过滤（可重复，格式 `provider/model`） |
| `--date <range>` | 日期范围：`today`、`week`、`month` |
| `--sort <field:dir>` | 排序（字段：task_name/agent_name/avg_reward/avg_duration_ms 等） |

### 使用示例（逐级钻取）

```bash
# 1. 列举所有实验
rockcli agent view -E

# 2. 列举指定实验的 Jobs
rockcli agent view -e exp-id

# 3. 按条件过滤和排序
rockcli agent view -e exp-id --agent claude-code --date today --sort avg_reward:desc

# 4. 全文搜索
rockcli agent view -e exp-id --q "codereview"

# 5. 查看 Jobs 下一页
rockcli agent view -e exp-id --limit 20 --offset 20

# 6. 查看某个 Job 详情（含 tasks 列表）
rockcli agent view -j my-job

# 7. 查看某个 Task 下的 Trials
rockcli agent view -j my-job -t my-task

# 8. 查看某个 Trial 详情
rockcli agent view -j my-job -t my-task -T trial-001

# 9. 查看 Trial 完整执行轨迹
rockcli agent view -j my-job --trajectory
```

### 行为说明

- `view -j J` 若只查到一个 task，会内联列出 trials 并展开首个 trial 的 Outcome/Tokens/Timing
- 查不到结构化元数据时，退避展示 job root 文件预览和 `agent fs` 下一步命令
- tasks 视图可推导时附上 Rock Console job 链接（pre 环境追加 `?env=pre`）

---

## fs

Agent job/trial 文件操作。支持 Job scope 和 Trial scope 两种作用域：
- **Job scope**：只指定 `-j`，操作 job 级别的文件
- **Trial scope**：同时指定 `-j` 和 `-t`，操作 trial 级别的文件

### fs ls

列出文件目录。

```bash
rockcli agent fs ls [path] -j <job> [-t <task>] [-T <trial>] [选项]
```

| 参数 | 说明 |
|------|------|
| `[path]` | Job scope: 透传 prefix 查询；Trial scope: 客户端按前缀过滤 |
| `-j, --job <name>` | Job 名（必填） |
| `-t, --task <name>` | Task 名（提供时切到 trial scope） |
| `-T, --trial <name>` | Trial 名（trial scope 下；仅 1 项时自动选） |
| `-e, --experiment <id>` | 实验 ID |
| `--pre` | 使用预发环境 |
| `-o, --output <fmt>` | 输出格式：table, json, simple |

```bash
# 列 job 根目录
rockcli agent fs ls -e exp-id -j my-job

# 按 prefix 列文件
rockcli agent fs ls codereview-x/agent -e exp-id -j my-job

# 列 trial 文件（自动选择唯一 trial）
rockcli agent fs ls -e exp-id -j my-job -t my-task
```

### fs cat

打印文本文件内容（二进制文件返回 BINARY_FILE 提示）。

```bash
rockcli agent fs cat <path> -j <job> [-t <task>]
```

| 参数 | 说明 |
|------|------|
| `<path>` | 文件路径（相对 scope root） |
| `-j, --job <name>` | Job 名（必填） |
| `-t, --task <name>` | Task 名（切换到 trial scope） |
| `-e, --experiment <id>` | 实验 ID |
| `--pre` | 使用预发环境 |

```bash
# Job scope：读取 job 级文件
rockcli agent fs cat codereview-x/agent/install.sh -e exp-id -j my-job

# Trial scope：读取 trial 级文件
rockcli agent fs cat agent/log.txt -e exp-id -j my-job -t my-task

# 读取 result.json
rockcli agent fs cat result.json -e exp-id -j my-job -t my-task
```

### fs download

下载文件到本地。

```bash
rockcli agent fs download <path> -j <job> [-t <task>] [-o local|-]
```

| 参数 | 说明 |
|------|------|
| `<path>` | 文件路径（相对 scope root） |
| `-j, --job <name>` | Job 名（必填） |
| `-t, --task <name>` | Task 名（trial scope） |
| `-e, --experiment <id>` | 实验 ID |
| `--pre` | 使用预发环境 |
| `-o <target>` | 落地路径；`-` = stdout；省略 = `~/.rock` 缓存 |

```bash
# 下载到指定目录
rockcli agent fs download bundle.zip -e exp-id -j my-job -t my-task -o /tmp/

# 输出到 stdout（可 pipe）
rockcli agent fs download trajectory.json -e exp-id -j my-job -t my-task -o -

# 下载到默认缓存目录
rockcli agent fs download run.log -e exp-id -j my-job
```

### fs artifacts

显示 trial artifacts（files 表 + manifest 块）。

```bash
rockcli agent fs artifacts -j <job> -t <task> [-e <experiment_id>] [--pre]
```

| 参数 | 说明 |
|------|------|
| `-j, --job <name>` | Job 名（必填） |
| `-t, --task <name>` | Task 名（必填） |
| `-e, --experiment <id>` | 实验 ID |
| `--pre` | 使用预发环境 |

```bash
# 展示 artifacts + manifest
rockcli agent fs artifacts -e exp-id -j my-job -t my-task
```

---

## deps

管理 Agent 运行时依赖。

### deps sync

同步依赖到 `~/.rock/packages`。

```bash
rockcli agent deps sync [package] [选项]
```

| 参数 | 说明 |
|------|------|
| `[package]` | 依赖名，默认 benchhub（当前仅支持 benchhub） |
| `--registry <url>` | npm registry 地址（默认 http://registry.npm.alibaba-inc.com） |
| `--force` | 即使本地版本已是最新，也强制重新安装 |

```bash
# 同步默认的 benchhub 依赖
rockcli agent deps sync

# 强制重新安装
rockcli agent deps sync benchhub --force
```

---

## bench

管理 benchhub 模板。

```bash
# 列出可用 bench 模板
rockcli agent bench list
```
