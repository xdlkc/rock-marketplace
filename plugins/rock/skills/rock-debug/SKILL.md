---
name: rock-debug
description: ROCK 沙箱排查工具。适用场景：沙箱启动失败、沙箱无响应、命令执行失败、exec 报错、沙箱状态异常、查看沙箱日志/log search/log tail、搜索错误日志、查看操作历史/history、回放请求/replay、在沙箱中执行排查命令/exec、定位沙箱错误原因。当用户提到沙箱报错、沙箱挂了、沙箱不可用、日志排查、log search、log tail、查看日志、排查问题、history、replay、exec 调试时使用。
---

# ROCK 沙箱排查指南

## Step 1：确认沙箱状态

所有排查的第一步，确认沙箱当前状态：

```bash
rockcli sandbox <id> status
```

状态流转：`pending` → `alive` → `stopping` → `stopped`

根据状态进入对应排查分支：

| 状态 | 含义 | 下一步 |
|------|------|--------|
| `alive` | 沙箱运行中 | → Step 2A：存活状态排查 |
| `pending` | 正在启动 | 等待，或检查是否卡住（超过 2 分钟未变 alive 视为启动失败） |
| `stopped` | 已停止 | → Step 2B：已停止状态排查 |
| `stopping` | 正在停止 | 等待停止完成后按 stopped 处理 |
| 无法获取状态 | ID 错误或沙箱已清理 | 确认 ID 是否正确，沙箱可能已被自动清理（auto-clear） |

---

## Step 2A：沙箱存活（alive）— 可交互排查

沙箱存活时可以使用全部排查手段。根据问题类型选择：

### 命令执行失败 / exec 报错

1. **重新执行并观察输出**：

```bash
rockcli sandbox <id> exec '<原始命令>'
```

2. **检查环境和依赖**：

```bash
rockcli sandbox <id> exec 'which python && python --version'
rockcli sandbox <id> exec 'pip list 2>&1 | head -20'
rockcli sandbox <id> exec 'df -h && free -h'            # 磁盘/内存
rockcli sandbox <id> exec 'cat /proc/cpuinfo | head -5'  # CPU
```

3. **搜索命令输出日志中的错误**：

```bash
rockcli sandbox <id> log search --log-file command.log -k "error" -C 5
rockcli sandbox <id> log search --log-file command.log -k "Traceback" -C 10
```

### 服务/进程异常

1. **检查进程状态**：

```bash
rockcli sandbox <id> exec 'ps aux'
rockcli sandbox <id> exec 'netstat -tlnp 2>/dev/null || ss -tlnp'
```

2. **查看系统组件日志**：

```bash
rockcli sandbox <id> log search --log-file rocklet.log -k "error" -C 3
rockcli sandbox <id> log search --log-file rocklet_uvicorn.log -k "error"
```

3. **实时追踪**（适合复现问题时使用）：

```bash
rockcli sandbox <id> log tail -k "error"
```

### 资源问题（OOM / 磁盘满）

```bash
rockcli sandbox <id> exec 'free -h'
rockcli sandbox <id> exec 'df -h'
rockcli sandbox <id> log search -m 60 -k "OOM"
rockcli sandbox <id> log search -m 60 -k "No space left"
```

### HTTP / 网络问题

```bash
rockcli sandbox <id> log search --log-file access.log -k "500"
rockcli sandbox <id> log search --log-file access.log -f "status>=400"
rockcli sandbox <id> exec 'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health'
```

### 查询历史与回放

存活状态的沙箱也可以查看操作历史和回放，用于追溯问题发生过程：

```bash
rockcli sandbox <id> history                    # 查看完整操作历史
rockcli sandbox <id> replay                     # 回放请求序列到新沙箱
```

适用场景：
- 回溯操作顺序，定位哪一步导致了当前异常
- 回放到新沙箱做对比，排除环境污染因素
- 导出操作序列供他人复现

---

## Step 2B：沙箱已停止（stopped）— 只能查历史

沙箱停止后无法 exec 或 tail，只能通过历史记录和日志回溯：

### 查看操作历史

回溯沙箱生命周期内所有 API 操作（start/exec/upload 等完整请求和响应）：

```bash
rockcli sandbox <id> history
```

重点关注：
- 最后几次 exec 的命令和返回结果
- 是否有异常的 HTTP 状态码（4xx/5xx）
- 操作时间线，定位问题发生节点

### 搜索历史日志

沙箱停止后日志仍可搜索：

```bash
rockcli sandbox <id> log search -k "error" -m 120      # 搜索最近 2 小时
rockcli sandbox <id> log search --log-file command.log -k "kill\|OOM\|signal"
rockcli sandbox <id> log search -f "level=ERROR"
```

### 回放请求序列

将历史请求在新沙箱中回放，用于复现问题：

```bash
rockcli sandbox <id> replay
```

回放会自动从该沙箱的历史中拉取请求序列并按顺序执行。适合：
- 验证问题是否可复现
- 在新环境中对比排查
- 确认修复后回归测试

### 下载日志文件

将日志下载到本地做更深入分析：

```bash
rockcli sandbox <id> log ls                          # 列出可用日志
rockcli sandbox <id> log download command.log        # 下载命令日志
rockcli sandbox <id> log download rocklet.log        # 下载系统日志
```

---

## 常见问题速查

| 问题 | 排查命令 |
|------|----------|
| 沙箱启动卡 pending | `status` 确认状态；检查镜像/资源配额；查 `rocklet.log` |
| exec 命令无输出/超时 | `log search --log-file command.log`；`exec 'ps aux'` 检查是否有僵尸进程 |
| OOM / 被 kill | `exec 'dmesg \| tail'`；`log search -k "OOM\|kill\|signal"` |
| 磁盘满 | `exec 'df -h'`；`exec 'du -sh /* 2>/dev/null \| sort -rh \| head'` |
| HTTP 5xx | `log search --log-file access.log -f "status>=500"`；检查服务进程是否存活 |
| 沙箱突然 stopped | `history` 查看最后操作；`log search -f "level=ERROR"` |
| 问题无法复现 | `history` 回溯操作序列；`replay` 在新沙箱回放 |

## 支持的日志文件

| 日志文件 | 说明 |
|----------|------|
| `command.log` | 命令输出 |
| `access.log` | HTTP 访问 |
| `rocklet.log` | 系统组件 |
| `rocklet_uvicorn.log` | Uvicorn 服务 |

详细日志命令参数见 [references/log.md](references/log.md)。
