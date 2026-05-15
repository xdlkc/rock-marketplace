---
name: rock-debug
description: ROCK 沙箱排查工具。适用场景：沙箱启动失败、沙箱无响应、命令执行失败、exec 报错、沙箱状态异常、查看沙箱日志/log search/log tail、搜索错误日志、查看操作历史/history、回放请求/replay、在沙箱中执行排查命令/exec、定位沙箱错误原因。当用户提到沙箱报错、沙箱挂了、沙箱不可用、日志排查、log search、log tail、查看日志、排查问题、history、replay、exec 调试时使用。
---

# ROCK 沙箱排查指南

## 核心原则

**只读诊断**：本指南所有命令仅用于观察，**绝不修改沙箱内部的文件或进程**。所有调查通过 `rockcli` 完成（日志、历史、状态、只读 exec）。唯一例外：用户明确要求修复沙箱内部内容时，需先获得用户确认。

**配套技能**：本指南聚焦排查流程，具体的 rockcli 命令参考见 [rock-cli](../rock-cli/SKILL.md)。

**渐进式确认**：诊断中如有猜测或推断，必须及时与用户确认。用户不认可则继续分析；用户认可且同意进一步分析才继续深入——**不要埋头苦干**。

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

> **日志来源提醒**：除沙箱内部日志（`rockcli sandbox <id> log search`）外，**集群维度日志**也是重要来源——它记录了沙箱在集群层面的事件（请求路由、调度、创建沙箱、停止沙箱 调用等）：
>
> ```bash
> rockcli log search -k <sandbox_id> -k <keyword> --raw -m <minutes>
> ```
>

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

> **日志来源提醒**：除沙箱内部日志（`rockcli sandbox <id> log search`）外，**集群维度日志**也是重要来源——它记录了沙箱在集群层面的事件（请求路由、调度、创建沙箱、停止沙箱 调用等）：
>
> ```bash
> rockcli log search -k <sandbox_id> -k <keyword> --raw -m <minutes>
> ```
>
> 当沙箱内部日志缺失或不完整时，请优先依赖集群维度日志进行回溯。

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

## 专项场景：接口调用失败的根因分析

**表现**：用户报告 `get_status` / `execute` / `create_session` / `run_in_session` / `upload` / `download` 等接口返回错误，常伴随沙箱已停止或不可达。

### Step 1：集群维度搜索 stop 事件

```bash
rockcli log search -k <sandbox_id> -k 'stop' --raw -m <minutes>
```

若时间窗口过小找不到日志，请尝试扩大 `-m` 参数。

### Step 2：判断停止原因

| 停止原因 | 判断依据 |
|---------|---------|
| 用户调用停止接口 | 上一步日志中出现 `POST /apis/envs/sandbox/v1/stop` |
| 自动过期 | 日志中存在 `sandbox_id:[{sandbox_id}] is expired`，该条目时间即停止时间 |
| 意外崩溃 | rocklet.log 或 command.log 在停止时间前出现 OOM / crash |

### Step 3：对比时间戳

- **停止时间 < 用户失败时间** → 用户自身行为异常（先调用 stop，再尝试使用沙箱）
- **没有用户停止操作，沙箱自行死亡** → 进入下一步根因分析

### Step 4：多日志根因深挖

```bash
# 系统组件日志
rockcli sandbox <id> log search --log-file rocklet.log -k "error\|OOM\|kill\|crash\|exit" -m <minutes>

# 命令执行日志
rockcli sandbox <id> log search --log-file command.log -k "error\|fail\|Exception" -m <minutes>

# HTTP 错误
rockcli sandbox <id> log search --log-file access.log -k "500\|502\|503\|504" -m <minutes>

# 完整请求时间线 + 当前状态
rockcli sandbox <id> history
rockcli sandbox <id> status
```

**额外：推断可疑命令**

除上述日志外，还需结合 `history` 与 `command.log`，**推断沙箱停止前执行的最近命令中哪些为可疑命令**——这些命令可能直接导致 rocklet 进程损坏、OOM 或文件系统异常。

```bash
# 拉取停止时间前 N 分钟的命令历史
rockcli sandbox <id> history -s <stop_time-N> -e <stop_time>

# 按时间段过滤命令日志
rockcli sandbox <id> log search --log-file command.log -s <stop_time-N> -e <stop_time>
```

常见可疑命令类型：
- **大内存分配**：加载超大模型、全量读入大文件、一次性 `cat` 巨型日志 → 触发 OOM Killer 杀掉 rocklet
- **fork 炸弹 / 进程风暴**：递归启动子进程、未限并发的并行测试 → 耗尽 PID 或内存
- **资源密集 IO**：`dd if=/dev/zero ...`、循环写入临时文件、未清理产物 → 磁盘满后 rocklet 写日志失败
- **直接信号操作**：`kill -9` / `pkill` 误伤 rocklet 自身或其依赖进程
- **修改系统配置**：改 `/etc`、卸载关键库、调整 `ulimit` 后再触发场景

按「渐进式确认」原则，推断出可疑命令后**先与用户确认怀疑对象**，再决定是否深挖具体命令逻辑。

### Step 5：输出过多时缩小时间窗口

```bash
rockcli sandbox <id> log search --log-file command.log -m 30  # 仅查最近 30 分钟
rockcli sandbox <id> log search --log-file rocklet.log -m 15
```

---

## 专项场景：磁盘占用过大诊断

**表现**：沙箱磁盘在某个时间段内迅速膨胀，用户询问原因。

### Step 1：获取命令执行历史或分析 command.log

```bash
# 搜索指定时间段内的命令执行历史
rockcli sandbox <id> history -s <start_time> -e <end_time>

# 搜索指定时间内的命令执行日志
rockcli sandbox <id> log search --log-file command.log -k <keyword> -s <start_time> -e <end_time>
```

重点关注 **磁盘用量激增时间段附近及之前** 执行的命令。

### Step 2：识别可疑命令

基于 Step 1 的命令情况，推测哪些命令会导致磁盘用量激增，**只需推测，不要直接深入**。优先关注以下两种常见场景：

1. **单元测试执行**
   - **特征**：任务正在执行单元测试（比如涉及 QuestDB 等数据库的测试），且测试逻辑中包含大量磁盘写入操作。
   - **行动**：若怀疑是此类原因，**不要直接深入分析**，先列出测试类的名称列表，并向用户确认:"是否分析该测试逻辑以获取根因？"
   - **注意**：仅在用户批准后，再深入分析具体的测试文件。

2. **手动大数据写入**
   - **特征**：用户执行了 `dd` 等命令进行大规模数据写入。

**处理逻辑**：
- 优先按照上述两个方向进行分析。
- 若排除上述情况，**不要再自行扩展分析方向**，而是向用户确认:"排除上述两种情况，是否从别的角度进行分析？"，仅用户批准后再根据具体命令特征分析其他潜在原因。

---

## 常见陷阱

- **输出过多**：缩小时间窗口（`-m`、`-s`、`-e`）、增加更具体的关键词、或用 `--log-file` 指定特定日志文件。
- **history 文件过大**：用 grep 过滤特定 API endpoint 的历史记录。
- **沙箱已停止**：`history` 和 `log` 命令仍然可用，无需依赖 exec。

---

## 常见问题速查

| 问题 | 排查命令 |
|------|----------|
| 沙箱启动卡 pending | `status` 确认状态；检查镜像/资源配额；查 `rocklet.log` |
| exec 命令无输出/超时 | `log search --log-file command.log`；`exec 'ps aux'` 检查是否有僵尸进程 |
| OOM / 被 kill | `exec 'dmesg \| tail'`；`log search -k "OOM\|kill\|signal"` |
| 磁盘满 | `exec 'df -h'`；`exec 'du -sh /* 2>/dev/null \| sort -rh \| head'` |
| HTTP 5xx | `log search --log-file access.log -f "status>=500"`；检查服务进程是否存活 |
| 沙箱突然 stopped | `history` 查看最后操作；`log search -f "level=ERROR"`；集群级 `rockcli log search -k <id> -k 'stop' --raw -m <min>` |
| 接口调用失败定位停止原因 | 集群级 `rockcli log search -k <id> -k 'stop' --raw -m <min>`，对比停止时间与失败时间 |
| 磁盘占用突然飙升 | `history -s <ts> -e <ts>` 拉取时间段内命令；优先怀疑单元测试 / `dd` 大数据写入 |
| 问题无法复现 | `history` 回溯操作序列；`replay` 在新沙箱回放 |

## 支持的日志文件

| 日志文件 | 说明 |
|----------|------|
| `command.log` | 命令输出 |
| `access.log` | HTTP 访问 |
| `rocklet.log` | 系统组件 |
| `rocklet_uvicorn.log` | Uvicorn 服务 |

详细日志命令参数见 [references/log.md](references/log.md)。
