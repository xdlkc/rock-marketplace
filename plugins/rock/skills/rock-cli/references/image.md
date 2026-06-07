# image 命令详细参数

镜像转储操作：将 Docker 镜像在仓库之间镜像 / 转储，并管理转储任务。

## 基本用法

```bash
rockcli image <子命令> [选项]
```

| 子命令 | 说明 |
|--------|------|
| `mirror` | 将 Docker 镜像从源仓库镜像到目标仓库 |
| `dump` | 通过沙箱传输 Docker 镜像 |
| `task` | 管理转储任务（list / status / resume / delete） |

> `mirror` 与 `dump` 的区别：`mirror` 面向「源仓库 → 目标仓库」的整体镜像，支持 remote/local 两种模式、并发沙箱、digest 校验与断点续传；`dump` 侧重通过沙箱把镜像推送到目标仓库（access-key 认证），更适合简单的批量转储。

---

## mirror - 仓库间镜像

```bash
rockcli image mirror [images..] [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `[images..]` | Docker 镜像名称（位置参数，可多个） | - |
| `--file, -f <path>` | 镜像列表输入文件（txt 或 jsonl 格式） | - |
| `--mode <mode>` | 执行模式：`remote`（沙箱）/ `local`（本地 Docker） | remote |
| `--concurrency, -c <num>` | 沙箱并发数（并行沙箱数，最少 3，默认按 CPU 核数计算） | auto |
| `--source-registry <url>` | 源仓库 URL | - |
| `--source-username <name>` | 源仓库用户名 | - |
| `--source-password <pass>` | 源仓库密码 | - |
| `--target-registry <url>` | 目标仓库 URL（**必需**） | - |
| `--target-username <name>` | 目标仓库用户名（私有仓库必需） | - |
| `--target-password <pass>` | 目标仓库密码（私有仓库必需） | - |
| `--namespace, -n <name>` | 目标命名空间（覆盖源命名空间） | - |
| `--repo <name>` | 目标仓库名（覆盖源仓库名） | - |
| `--retry <num>` | 失败传输的重试次数 | 3 |
| `--resume` | 从进度文件恢复 | false |
| `--progress-file <path>` | 进度文件路径 | - |
| `--quiet, -q` | 静默输出 | false |
| `--skip-pull-if-exists` | 本地/沙箱中镜像已存在则跳过 pull | false |
| `--force, -F` | 即使目标 digest 相同也强制重新传输 | false |
| `--enable-digest-check` | 拉取源镜像后再校验一次 digest | false |
| `--skip-auto-clear` | 仅 remote 模式生效：push 成功后不在沙箱内执行 `docker rmi` + `docker image prune`（默认开启清理，避免沙箱磁盘打满）；local 模式默认不自动清理 | false |

```bash
# 镜像单个镜像
rc image mirror nginx:latest \
  --target-registry registry.example.com \
  --target-username user --target-password pass

# 从文件批量镜像
rc image mirror -f images.jsonl \
  --target-registry registry.example.com \
  --target-username user --target-password pass

# 并发传输（10 个并行沙箱）
rc image mirror -f images.jsonl -c 10 --mode remote \
  --target-registry registry.example.com \
  --target-username user --target-password pass

# 使用本地 Docker 镜像（无需沙箱）
rc image mirror nginx:latest --mode local \
  --target-registry registry.example.com \
  --target-username user --target-password pass

# 覆盖目标命名空间/仓库名
rc image mirror nginx:latest -n myns --repo mynginx \
  --target-registry registry.example.com \
  --target-username user --target-password pass
```

---

## dump - 通过沙箱转储镜像

```bash
rockcli image dump [images..] [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `[images..]` | Docker 镜像名称（位置参数，可多个） | - |
| `--file, -f <path>` | 镜像列表输入文件 | - |
| `--output-registry <url>` | 目标仓库地址 | - |
| `--namespace <name>` | 目标命名空间 | - |
| `--access-key-id <id>` | 仓库认证的访问密钥 ID | - |
| `--access-key-secret <secret>` | 仓库认证的访问密钥 | - |
| `--sandbox-mode <mode>` | 沙箱执行模式 | batch |
| `--concurrency, -c <num>` | 并发传输级别 | 1 |
| `--retry <num>` | 失败传输的重试次数 | 3 |
| `--resume` | 从进度文件恢复 | false |
| `--progress-file <path>` | 进度文件路径 | - |
| `--quiet, -q` | 静默输出 | false |
| `--skip-auto-clear` | push 成功后不在沙箱内执行 `docker rmi <source> <target>` + `docker image prune`（默认开启以释放沙箱磁盘，避免连续多镜像 dump 撑爆 `/var/lib/docker`） | false |

```bash
# 转储单个镜像
rc image dump nginx:latest

# 转储多个镜像
rc image dump nginx:latest python:3.11

# 从文件转储
rc image dump --file images.txt

# 并行转储
rc image dump -f images.txt --concurrency 2
```

---

## task - 管理转储任务

```bash
rockcli image task <task-action> [task-id] [选项]
```

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `<task-action>` | 任务动作：`list` / `status` / `resume` / `delete` | - |
| `[task-id]` | 任务 ID（status / resume / delete 时必填） | - |
| `--verbose, -v` | status 动作下打印每条镜像的结果与错误 | false |

```bash
# 列出所有转储任务
rc image task list

# 查看任务状态
rc image task status <task-id>

# 查看任务状态（含每条镜像详情）
rc image task status <task-id> -v

# 恢复失败的任务
rc image task resume <task-id>

# 删除指定任务
rc image task delete <task-id>
```
