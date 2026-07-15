# datasets 命令详细参数

管理 ROCK 数据集：列出、查看详情、查询任务、上传、文件操作。

## 目录

- [list - 列出数据集](#list)
- [detail - 查看数据集详情](#detail)
- [splits - 查看 split 列表](#splits)
- [tasks - 查询任务列表](#tasks)
- [task - 查看单个任务详情](#task)
- [upload - 上传数据集](#upload)
- [fs - 文件操作](#fs)

---

## 通用选项

| 参数 | 说明 |
|------|------|
| `--org <name>` | 组织名 |
| `--dataset <name>` | 数据集名称 |
| `--split <name>` | 数据集 split/version 名称（默认 `test`） |
| `--pre / --prod` | 选择环境（预发或生产，默认预发） |
| `--mode <local\|remote>` | 执行模式（本地或 ROCK 沙箱内执行，默认 local） |
| `--stop-sandbox` | remote 模式执行后停止复用沙箱 |
| `--output json` | JSON 格式输出 |

数据集可用 `org/dataset` 或 `--org`+`--dataset` 两种方式指定。

---

## list

列出数据集。

```bash
rc datasets list [选项]
```

| 参数 | 说明 |
|------|------|
| `-l, --limit <n>` | 返回数据集数量上限（默认 20） |
| `-o, --offset <n>` | 跳过前 N 个数据集（默认 0） |
| `--depth <1\|2>` | 列表深度：1 列出 orgs，2 列出 orgs 和 datasets |

```bash
rc datasets list
rc datasets list --prod
rc datasets list --limit 50
```

---

## detail

查看数据集详情。

```bash
rc datasets <dataset_name> [detail] [选项]
rc datasets detail --org <name> --dataset <name> [选项]
```

省略 action 时默认为 detail。

```bash
rc datasets my-org/swe-bench
rc datasets swe-bench detail --org my-org
```

---

## splits

查询数据集 split 列表。

```bash
rc datasets <dataset_name> splits [选项]
rc datasets splits --org <name> --dataset <name> [选项]
```

```bash
rc datasets my-org/swe-bench splits
```

---

## tasks

查询数据集任务列表（支持分页、搜索、排序）。

```bash
rc datasets <dataset_name> tasks [选项]
rc datasets tasks --org <name> --dataset <name> [选项]
```

| 参数 | 说明 |
|------|------|
| `-l, --limit <n>` | 返回任务数量上限（默认 20） |
| `-o, --offset <n>` | 跳过前 N 条任务（默认 0） |
| `--filter <query>` | 按 task name 模糊搜索 |
| `--sort-by <field>` | 排序字段：`name`、`created_at`、`updated_at` |
| `--sort-order <asc\|desc>` | 排序方向（默认 asc） |

```bash
rc datasets my-org/swe-bench tasks
rc datasets my-org/swe-bench tasks --split v1 --filter "astropy" --sort-by updated_at --sort-order desc
rc datasets my-org/swe-bench tasks --limit 50 --offset 20
rc datasets tasks --org my-org --dataset swe-bench --output json
```

---

## task

查看单个任务详情。

```bash
rc datasets <dataset_name> task --task <task_id> [选项]
rc datasets <dataset_name> task <task_id> [选项]
```

```bash
rc datasets my-org/swe-bench task --task astropy__astropy-7606 --split test
rc datasets my-org/swe-bench task astropy__astropy-7606
```

---

## upload

上传本地任务目录或从 Hugging Face 导入数据集。

```bash
rc datasets <dataset_name> upload <path> [选项]
rc datasets upload --org <name> --dataset <name> --dir <path> [选项]
```

### 本地上传参数

| 参数 | 说明 |
|------|------|
| `--dir <path>` | 本地任务目录 |
| `--concurrency <n>` | 上传并发数，范围 1-64（默认 4） |
| `-f, --force` | 覆盖已存在 task |

### Hugging Face 导入参数

| 参数 | 说明 |
|------|------|
| `--from hf` | 从 Hugging Face 转储数据集 |
| `--hf-name <repo>` | Hugging Face dataset repo id（默认 `<org>/<dataset>`） |
| `--hf-token <token>` | Hugging Face token（也可通过 `HF_TOKEN` 提供） |
| `--hf-split <split>` | Hugging Face 源 split（默认等于 --split） |
| `--hf-config <name>` | Hugging Face dataset config/subset |
| `--hf-revision <rev>` | Hugging Face branch、tag 或 commit |
| `--hf-layout <type>` | 落盘形态：`auto`（默认）、`files`、`rows`、`archive` |
| `--hf-task <id>` | 只转储指定 task id（可重复） |
| `--hf-tasks <file>` | 从文件读取 task id（一行一个） |
| `--resume` | 恢复之前中断的 HF 上传 |
| `--progress-file <path>` | 恢复的 run 目录或 progress.jsonl 路径 |
| `--task-id-field <field>` | rows/archive layout 中作为 ROCK task id 的字段 |
| `--staging-dir <path>` | HF 本地转储 staging 目录 |
| `--keep-staging` | 上传后保留 staging 目录 |

```bash
# 本地上传
rc datasets my-org/swe-bench upload ./tasks --split v1
rc datasets upload --org my-org --dataset swe-bench --dir ./tasks --concurrency 8 --force

# 从 Hugging Face 导入
HF_TOKEN=xxx rc datasets upload --org my-org --dataset swe-bench --split test \
  --from hf --hf-name SWE-bench/SWE-bench --hf-split test

# 只导入指定任务
HF_TOKEN=xxx rc datasets upload --org my-org --dataset swe-bench --split test \
  --from hf --hf-name SWE-bench/SWE-bench --hf-task astropy__astropy-12907

# 在沙箱内从 HF 下载并上传
HF_TOKEN=xxx rc datasets upload --org my-org --dataset terminal-bench --split test \
  --from hf --hf-layout files --mode remote
```

---

## fs

查看或下载单个任务下的文件。别名：`files`。

### fs ls

列出任务目录下的文件。

```bash
rc datasets <dataset_name> fs ls --task <task_id> [选项]
```

| 参数 | 说明 |
|------|------|
| `--task <task_id>` | 任务 ID（必填） |
| `--path <path>` | 任务内相对目录路径 |

```bash
rc datasets my-org/swe-bench fs ls --task task-1
rc datasets my-org/swe-bench fs ls --task task-1 --path logs
```

### fs get

查看任务文件内容。

```bash
rc datasets <dataset_name> fs get --task <task_id> --path <path> [选项]
```

```bash
rc datasets my-org/swe-bench fs get --task task-1 --path result.json
```

### fs download

下载单个任务文件或目录。

```bash
rc datasets <dataset_name> fs download --task <task_id> --path <path> --dest <path> [选项]
```

| 参数 | 说明 |
|------|------|
| `--task <task_id>` | 任务 ID（必填） |
| `--path <path>` | 任务内相对文件或目录路径（必填） |
| `--dest <path>` | 本地目标文件或目录（必填） |

```bash
rc datasets my-org/swe-bench fs download --task task-1 --path logs/out.txt --dest ./out.txt
```
