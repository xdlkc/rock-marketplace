---
name: rock-cli
description: ROCK CLI 使用指南。适用场景：安装/更新 rockcli、起沙箱/启动沙箱、停止沙箱、在沙箱里执行命令/exec、上传文件到沙箱、从沙箱下载文件、连接沙箱/attach/交互式 REPL、查看沙箱历史/history、回放请求/replay、查看状态/status、运行 AI Agent 评估任务。当用户提到 sandbox、rockcli、rc 命令、沙箱操作、agent 评估时使用。
---

# ROCK CLI 使用指南

## 安装与更新

```bash
# 安装
bash -c "$(curl -fsSL http://xrl.alibaba-inc.com/install.sh)"

# 升级（推荐）
rockcli update
```

安装后可用 `rockcli` 或 `rc`。小版本自动升级，major/minor 需手动升级。

### 认证配置

```bash
export ROCK_API_KEY=your-api-key          # 方式一：环境变量（优先级最高）
rockcli --api-key your-key <command>      # 方式二：全局参数
# 方式三：配置文件 ~/.rock/setting.json
```

---

## 场景指南

详细参数见 [references/sandbox.md](references/sandbox.md)。

### 场景一：快速体验 / 一次性任务

适用：临时执行脚本、验证环境、跑一段代码

```bash
rockcli sandbox start --wait-for-alive      # 启动并阻塞等待 alive
rockcli sandbox <id> exec 'python -c "print(1+1)"'
rockcli sandbox <id> stop
```

### 场景二：上传代码 → 执行 → 下载结果

适用：在沙箱中运行本地项目、批处理任务

```bash
rockcli sandbox start --memory 16g --cpus 4 --wait-for-alive

# 递归上传（注意：-r 短参数无效，必须用 --recursive）
rockcli sandbox <id> upload --dir ./my-project --target-path /app --recursive
# 包含隐藏文件（如 .env）加 -a
rockcli sandbox <id> upload --dir ./my-project --target-path /app --recursive -a

rockcli sandbox <id> exec 'cd /app && python main.py'
rockcli sandbox <id> download --file /app/output.csv   # 下载到当前目录
rockcli sandbox <id> stop
```

### 场景三：交互式开发（attach REPL）

适用：调试、探索环境、需要多轮交互（沙箱需处于 alive 状态）

```bash
rockcli sandbox <id> attach
```

REPL 内置命令见 [references/sandbox.md - attach](references/sandbox.md#attach)。关键区别：
- `/exit` — 断开连接，沙箱和会话保留，可重连
- `/close` — 永久关闭会话

### 场景四：查看历史操作记录

适用：回溯沙箱的所有 API 操作（start/exec/upload 等完整 HTTP 请求历史）

```bash
rockcli sandbox <id> history
```

### 场景五：回放请求

适用：重现历史请求序列，用于测试或复现问题

```bash
# 自动从该沙箱的日志历史中拉取请求并回放
rockcli sandbox <id> replay
```

### 场景六：查看沙箱状态

```bash
rockcli sandbox <id> status
```

状态流转：`pending` → `alive` → `stopping` → `stopped`

### 场景七：运行 AI Agent 评估任务

适用：通过 Python rock-sdk 执行 AI agent 评估任务（需要 Python >= 3.10）

```bash
# 从配置文件运行评估任务
rockcli agent run -c job.yaml

# 运行指定的单个任务
rockcli agent run -c job.yaml -t astropy__astropy-7606

# 使用预发环境运行评估任务
rockcli agent run -c job.yaml --pre
```

详细参数见 [references/agent.md](references/agent.md)。

---

## 全局选项

| 选项 | 说明 |
|------|------|
| `--verbose, -v` | 日志级别（-v: warning, -vv: info, -vvv: debug） |
| `--base-url <url>` | 服务端地址（默认 http://xrl.alibaba-inc.com） |
| `--api-key <key>` | API 密钥 |
| `--cluster <id>` | 集群标识 |
| `-H, --extra-header` | 额外 HTTP 请求头（格式：`Key=Value`） |
