# sandbox 命令详细参数

## 目录

- [start - 启动沙箱](#start)
- [stop - 停止沙箱](#stop)
- [restart - 重启沙箱](#restart)
- [exec - 执行命令](#exec)
- [status - 查看状态](#status)
- [upload - 上传文件](#upload)
- [download - 下载文件](#download)
- [attach - 交互式 REPL](#attach)
- [fs - 文件系统操作](#fs)
- [log - 日志操作](#log)
- [history - 历史记录](#history)

---

## start

```bash
rockcli sandbox start [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--image <name>` | Docker 镜像地址 | hub.docker.alibaba-inc.com/chatos/python:3.11 |
| `--memory <size>` | 内存限制（正数按 GiB 处理，支持 g/m 单位） | 8g |
| `--cpus <num>` | CPU 限制 | 2 |
| `--disk <size>` | 磁盘大小（正数按 GiB 处理，支持 g/m 单位） | 50g |
| `--timeout <sec>` | 启动超时（秒） | 300 |
| `--auto-clear <sec>` | 自动清理时间（秒） | 300 |
| `--auto-delete <sec>` | 自动删除秒数（0=立即，默认 1 天） | 86400 |
| `--image-os <os>` | 沙箱操作系统（`linux` / `windows`） | linux |
| `--num-gpus <n>` | GPU 数量 | - |
| `--accelerator-type <type>` | 加速器类型 | - |
| `--registry-username <user>` | 拉取镜像的 registry 用户名 | - |
| `--registry-password <pass>` | 拉取镜像的 registry 密码 | - |
| `--limit-cpus <n>` | CPU 硬限制上限（独立于 --cpus） | - |
| `--use-kata-runtime` | 使用 Kata Containers 运行时 | false |
| `--wait-for-alive` | 等待沙箱变为 alive 状态 | - |
| `--pre` | 使用预发环境 | - |
| `-o, --output <format>` | 输出格式（table / json） | table |

```bash
rockcli sandbox start
rockcli sandbox start --memory 16g --cpus 4 --disk 100g
rockcli sandbox start --wait-for-alive
rockcli sandbox start --cluster zb-a --wait-for-alive
rockcli sandbox start --image-os windows    # Windows 沙箱
rockcli sandbox start --output json         # JSON 格式输出
```

---

## stop

```bash
rockcli sandbox <id> stop [--output json]
```

---

## restart

重启已停止的沙箱实例。

```bash
rockcli sandbox <id> restart [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--wait-for-alive` | 等待沙箱就绪后再返回 | false |
| `--timeout <sec>` | 等待超时时间（秒） | 300 |
| `-o, --output <format>` | 输出格式（table / json） | table |

```bash
rockcli sandbox <id> restart
rockcli sandbox <id> restart --wait-for-alive
rockcli sandbox <id> restart --wait-for-alive --timeout 120
```

---

## exec

```bash
rockcli sandbox <id> exec '<command>' [--output json]
# 别名：execute
```

```bash
rockcli sandbox <id> exec 'ls -la'
rockcli sandbox <id> exec 'python script.py --arg1 value1'
rockcli sandbox <id> exec 'echo hello' --output json
```

---

## status

查看沙箱运行状态和 VNC 地址。支持查询已停止/已删除沙箱的状态。

```bash
rockcli sandbox <id> status [--output json] [--pre]
```

状态输出分段展示并包含 state timeline。

---

## upload

```bash
rockcli sandbox <id> upload [选项]
```

| 参数 | 说明 |
|------|------|
| `--file <path>` | 本地文件路径（与 `--dir` 互斥） |
| `--dir, -d <path>` | 本地目录路径（与 `--file` 互斥） |
| `--target-path <path>` | 目标路径（必填） |
| `--recursive` | 递归上传子目录（**`-r` 短参数无效，必须用 `--recursive`**） |
| `-a, --all` | 包含隐藏文件 |
| `-n, --no-clobber` | 不覆盖已存在的文件 |
| `-i, --interactive` | 覆盖前提示确认 |
| `--upload-mode <mode>` | 上传模式：auto（默认，>1MB 用 OSS）、direct（HTTP）、oss |

```bash
# 上传单个文件
rockcli sandbox <id> upload --file local.txt --target-path /tmp/remote.txt

# 上传目录（一级）
rockcli sandbox <id> upload --dir ./src --target-path /app/src

# 递归上传目录（注意：-r 短参数无效，必须用 --recursive）
rockcli sandbox <id> upload --dir ./project --target-path /app --recursive

# 包含隐藏文件
rockcli sandbox <id> upload --dir ./config --target-path /app/config -a
```

---

## download

```bash
rockcli sandbox <id> download --file <remote-path> [--local-path <path>] [--download-mode <auto|direct|oss>]
```

```bash
rockcli sandbox <id> download --file /tmp/output.txt
rockcli sandbox <id> download --file /tmp/output.txt --local-path ./local-output.txt
```

---

## attach

连接到沙箱，进入交互式 REPL 模式（沙箱需处于 alive 状态）。

```bash
rockcli sandbox <id> attach
```

REPL 内置命令（以 `/` 开头）：

| 命令 | 说明 |
|------|------|
| `/status` | 查看沙箱状态 |
| `/upload` | 上传文件 |
| `/download` | 下载文件 |
| `/log` | 查看日志 |
| `/stats` | 查看资源统计 |
| `/copy` | 复制上条输出到剪贴板 |
| `/retry` | 重试上次失败的命令 |
| `/sessions` | 列出当前会话 |
| `/clear` | 清屏 |
| `/exit` | 断开连接（沙箱和会话保留，可重连） |
| `/close` | 永久关闭会话并退出 |
| `/help` | 查看全部命令 |

---

## fs

沙箱文件系统操作。

```bash
rockcli sandbox <id> fs ls [path]          # 列出目录
rockcli sandbox <id> fs cat <path>         # 查看文件内容
rockcli sandbox <id> fs download <path>    # 下载文件
```

| 参数 | 说明 |
|------|------|
| `--host-ip <ip>` | 沙箱宿主机 IP（沙箱已销毁时使用） |
| `-s, --short` | 短格式输出（仅文件名） |
| `-o, --output <path>` | download: 本地保存路径 |

```bash
rockcli sandbox <id> fs ls /tmp
rockcli sandbox <id> fs cat /tmp/output.txt
rockcli sandbox <id> fs download /tmp/output.txt -o ./local.txt
```

---

## log

沙箱日志操作，格式：`rockcli sandbox <id> log <subcommand>`

### log search

```bash
rockcli sandbox <id> log search [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--log-file` | 日志文件名（command.log / access.log / rocklet.log / rocklet_uvicorn.log）。**注意：不支持位置参数，必须用 `--log-file`** | - |
| `-k, --keyword` | 搜索关键词（可多次指定） | - |
| `-f, --field` | 字段过滤（`field=value` 或 `field!=value`） | - |
| `-q, --query` | 直接指定 query_string（优先于 -k/-f） | - |
| `-A` | 显示匹配后 n 行 | - |
| `-B` | 显示匹配前 n 行 | - |
| `-C` | 显示匹配前后各 n 行 | - |
| `-m, --minutes` | 最近 N 分钟 | 15 |
| `-s, --start-time` | 开始时间（时间戳/相对时间/ISO 日期） | - |
| `-e, --end-time` | 结束时间 | - |
| `-l, --limit` | 限制每个日志文件返回数量 | 100 |
| `-o, --offset` | 跳过前 N 条（分页） | 0 |
| `--raw` | 显示原始输出（包含所有字段） | false |
| `--log-format` | 输出格式（logfmt / json / columns） | logfmt |
| `--columns` | 过滤显示字段（逗号分隔） | - |
| `--multilines` | 移除转义符，允许多行展示 | false |
| `--truncate` | 截断长字段值（0 禁用） | 2048 |
| `--count` | 只显示条数 | false |
| `--group-by` | 按字段分组（file / ip / app / hostname / cluster） | - |

```bash
# 搜索错误日志
rockcli sandbox <id> log search -k "error"

# 指定日志文件（必须用 --log-file，不支持位置参数）
rockcli sandbox <id> log search --log-file command.log

# 关键词 + 上下文
rockcli sandbox <id> log search --log-file command.log -k "error" -C 5

# 字段过滤
rockcli sandbox <id> log search -f "level=ERROR" -f "status>=500"

# 搜索最近30分钟
rockcli sandbox <id> log search -m 30 -k "timeout"

# 按文件分组
rockcli sandbox <id> log search --group-by file
```

### log tail

```bash
rockcli sandbox <id> log tail [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-k, --keyword` | 过滤关键词 | - |
| `-i, --interval` | 刷新间隔（秒） | 5 |

```bash
rockcli sandbox <id> log tail
rockcli sandbox <id> log tail -k "error"
rockcli sandbox <id> log tail -k "error" -i 3
```

### log ls

列出沙箱中可用的日志文件。

```bash
rockcli sandbox <id> log ls
```

### log download

下载沙箱日志文件到本地。

```bash
rockcli sandbox <id> log download <remote-log-path>
```

```bash
# 下载命令输出日志
rockcli sandbox <id> log download command.log

# 下载访问日志
rockcli sandbox <id> log download access.log
```

---

## history

查看沙箱所有 API 操作的完整 HTTP 请求/响应历史（包含 start、exec、upload、download 等）。

```bash
rockcli sandbox <id> history
```
