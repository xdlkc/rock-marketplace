# experiment 命令详细参数

实验沙箱管理。别名：`expr`、`exp`。

## 基本用法

```bash
rockcli experiment <experiment_id> [子命令] [选项]
rockcli expr <experiment_id> [子命令] [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `<experiment_id>` | 实验 ID（必填） | - |
| `--page <num>` | 摘要使用的页码 | 1 |
| `--size <num>` | 摘要使用的每页条数 | 20 |
| `--status <status>` | 状态过滤，逗号分隔 | RUNNING,PENDING |
| `-o, --output <format>` | 输出格式：table, json | table |

默认只查询 RUNNING,PENDING 状态，Total 为过滤后的数量。

```bash
# 查看实验沙箱总数、当前页分布
rc expr aone-bench-test

# 指定查看所有状态
rc expr aone-bench-test --status RUNNING,PENDING,STOPPED
```

---

## sandboxes - 查询实验下的沙箱列表

```bash
rockcli experiment <experiment_id> sandboxes [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--page <num>` | 页码（从 1 开始） | 1 |
| `--size <num>` | 每页条数 | 20 |
| `--status <status>` | 状态过滤，逗号分隔 | RUNNING,PENDING |
| `-o, --output <format>` | 输出格式：table, json | table |

```bash
# 查询实验下第一页沙箱
rc expr aone-bench-test sandboxes

# 查询下一页
rc expr aone-bench-test sandboxes --page 2 --size 20

# 查询所有状态的沙箱
rc expr aone-bench-test sandboxes --status RUNNING,PENDING,STOPPED
```

---

## sandboxes stop - 批量停止实验下的沙箱

```bash
rockcli experiment <experiment_id> sandboxes stop [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--status <status>` | 状态过滤，只停止匹配的沙箱 | RUNNING,PENDING |
| `--dry-run` | 只打印影响范围，不执行停止 | - |
| `-y, --yes` | 跳过二次确认 | - |
| `--concurrency <num>` | 并发停止请求数 | 5 |
| `--fetch-concurrency <num>` | 并发分页拉取请求数 | 5 |
| `--size <num>` | 内部翻页拉取时每页条数 | 100 |

```bash
# 预览会停止的沙箱数量（不实际停止）
rc expr aone-bench-test sandboxes stop --dry-run

# 并发停止并跳过确认
rc expr aone-bench-test sandboxes stop -y --concurrency 10

# 只停止 RUNNING 状态的沙箱
rc expr aone-bench-test sandboxes stop --status RUNNING -y
```
