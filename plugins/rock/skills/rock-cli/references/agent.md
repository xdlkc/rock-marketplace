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

| 参数 | 说明 |
|------|------|
| `--config <path>` | JobConfig YAML 配置文件路径（Config 模式必需） |
| `--bench <name>` | Bench 名称（Bench 模式必需，来自 benchhub 模板） |
| `--dataset <name>` | 数据集名称（优先于 `--set datasets.0.name`） |
| `--split <name>` | 数据集 split/version 名称（映射到 `datasets.0.registry.split`） |
| `--task <name>` | 任务名称（Bench 模式必传；Config 模式可省略并使用 YAML 中的 `datasets.0.task_names`） |
| `--agent <name>` | Agent 名称（优先于 `--set agents.0.name`） |
| `--model <name>` | 模型名称（优先于 `--set agents.0.model_name`） |
| `--pre` | 使用预发环境 |
| `--async` | 异步模式：提取 sandbox_id 后退出 |
| `--ee <KEY=VALUE>` | 沙箱环境变量，可多次指定 |
| `--set <path=value>` | YAML 字段覆盖，数组用 `.数字` 表示下标 |

```bash
# Config 模式：从本地 YAML 文件运行
rockcli agent run --config job.yaml

# 覆盖 YAML 中的任务和资源字段
rockcli agent run --config job.yaml --task crack-7z-hash --set environment.cpus=8

# Bench 模式：从 benchhub 模板运行（--task 必传）
rockcli agent run --bench aone-bench --task codereview-20789198

# Bench 模式：指定 Agent 和 Model
rockcli agent run --bench aone-bench --task codereview-20789198 --agent claude-code --model claude-sonnet-4-6

# 异步模式（提交后立即返回 sandbox_id）
rockcli agent run --config job.yaml --async

# 注入沙箱环境变量
rockcli agent run --config job.yaml --ee API_KEY=sk-xxx --ee DEBUG=1
```

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

### 使用示例（逐级钻取）

```bash
# 1. 列举所有实验
rockcli agent view -E

# 2. 列举指定实验的 Jobs
rockcli agent view -e exp-id

# 3. 查看 Jobs 下一页
rockcli agent view -e exp-id --limit 20 --offset 20

# 4. 查看某个 Job 详情（含 tasks 列表）
rockcli agent view -j my-job

# 5. 查看某个 Task 下的 Trials
rockcli agent view -j my-job -t my-task

# 6. 查看某个 Trial 详情
rockcli agent view -j my-job -t my-task -T trial-001

# 7. 查看 Trial 完整执行轨迹
rockcli agent view -j my-job --trajectory
```

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
