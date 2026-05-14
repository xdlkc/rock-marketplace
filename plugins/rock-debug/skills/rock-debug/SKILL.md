---
name: rock-debug
description: ROCK 沙箱排查工具。适用场景：沙箱命令执行失败、查看沙箱日志/log search/log tail/log ls/log download、搜索错误日志、实时追踪日志、下载日志文件、定位沙箱错误原因。当用户提到沙箱报错、日志排查、log search、log tail、查看日志、排查问题时使用。
---

# ROCK 沙箱排查指南

适用：沙箱中命令执行失败、需要定位错误原因。

## 日志搜索

```bash
# 搜索所有日志（默认最近 15 分钟）
rockcli sandbox <id> log search -k "error"

# 指定日志文件（必须用 --log-file，位置参数无效）
rockcli sandbox <id> log search --log-file command.log -k "error"
rockcli sandbox <id> log search --log-file access.log -k "500"

# 显示上下文 / 扩大时间范围 / 字段过滤
rockcli sandbox <id> log search --log-file command.log -k "error" -C 5
rockcli sandbox <id> log search -m 60 -k "OOM"
rockcli sandbox <id> log search -f "level=ERROR"
```

## 实时追踪

```bash
rockcli sandbox <id> log tail -k "error"
rockcli sandbox <id> log tail -k "error" -i 3   # 每 3 秒刷新
```

## 列出日志文件

```bash
rockcli sandbox <id> log ls
```

## 下载日志文件

```bash
rockcli sandbox <id> log download <remote-log-path>
```

## 支持的日志文件

| 日志文件 | 说明 |
|----------|------|
| `command.log` | 命令输出 |
| `access.log` | HTTP 访问 |
| `rocklet.log` | 系统组件 |
| `rocklet_uvicorn.log` | Uvicorn 服务 |

## 排查流程

1. `rockcli sandbox <id> status` — 确认沙箱状态是否 alive
2. `rockcli sandbox <id> log ls` — 列出可用日志文件
3. `rockcli sandbox <id> log search -k "error"` — 搜索错误关键词
4. `rockcli sandbox <id> log search --log-file command.log -k "error" -C 5` — 查看错误上下文
5. `rockcli sandbox <id> log tail -k "error"` — 实时追踪（适合复现问题）

详细参数见 [references/log.md](references/log.md)。
