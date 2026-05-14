# log 命令详细参数

沙箱日志操作，格式：`rockcli sandbox <id> log <subcommand>`

## log search

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

## log tail

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

## log ls

列出沙箱中可用的日志文件。

```bash
rockcli sandbox <id> log ls
```

## log download

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
