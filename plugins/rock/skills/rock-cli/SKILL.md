---
name: rock-cli
description: rockcli（rc）命令使用指南，覆盖沙箱、agent 评估、实验、镜像等全部操作。用途：查 rc 命令的用法 / 参数，或用 rc 操作沙箱（起停、exec、上传下载、attach、history、replay、status）、运行与查看 agent 评估（agent run / view / fs）、管理实验（experiment / expr）、转储镜像（image mirror / dump / task）。当用户提到 rockcli、rc 命令、sandbox 操作、agent view、experiment、镜像搬运等时使用。
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

适用：通过 Python rock-sdk 执行 AI agent 评估任务（需要 Python >= 3.11）

```bash
# Config 模式：从本地 YAML 文件运行
rockcli agent run --config job.yaml

# 覆盖 YAML 中的任务
rockcli agent run --config job.yaml --task astropy__astropy-7606

# Bench 模式：从 benchhub 模板运行
rockcli agent run --bench aone-bench --task codereview-20789198 --agent claude-code

# 异步模式（提交后立即返回 sandbox_id）
rockcli agent run --config job.yaml --async

# 使用预发环境
rockcli agent run --config job.yaml --pre
```

### 场景八：查看 Agent Job/Task/Trial 信息

适用：查看实验列表、Job 状态、Task 进度、Trial 结果和执行轨迹

```bash
# 列举所有实验
rockcli agent view -E

# 列举指定实验的 Jobs
rockcli agent view -e exp-id

# 查看 Job 详情
rockcli agent view -j my-job

# 查看 Trial 完整执行轨迹
rockcli agent view -j my-job --trajectory
```

### 场景九：Agent 文件操作（查看/下载 Job 产物）

适用：查看 job/trial 的文件列表、读取日志和结果文件、下载产物、查看 artifacts

```bash
# 列出 job 根目录文件
rockcli agent fs ls -e exp-id -j my-job

# 读取 trial 的 result.json
rockcli agent fs cat result.json -e exp-id -j my-job -t my-task

# 下载 trajectory 到本地
rockcli agent fs download trajectory.json -e exp-id -j my-job -t my-task -o /tmp/

# 查看 trial artifacts 和 manifest
rockcli agent fs artifacts -e exp-id -j my-job -t my-task
```

### 场景十：实验沙箱管理（批量查看/停止）

适用：查看实验下的沙箱列表、批量停止实验的所有沙箱

```bash
# 查看实验沙箱概况
rc expr aone-bench-test

# 查询实验下沙箱列表
rc expr aone-bench-test sandboxes

# 预览批量停止影响范围
rc expr aone-bench-test sandboxes stop --dry-run

# 批量停止并跳过确认
rc expr aone-bench-test sandboxes stop -y --concurrency 10
```

### 场景十一：镜像转储（仓库间镜像 / 沙箱传输）

适用：将 Docker 镜像从源仓库镜像到目标仓库、通过沙箱批量搬运镜像、管理转储任务

```bash
# 仓库间镜像单个镜像（mirror）
rc image mirror nginx:latest \
  --target-registry registry.example.com \
  --target-username user --target-password pass

# 从文件批量镜像 + 并发沙箱
rc image mirror -f images.jsonl -c 10 --mode remote \
  --target-registry registry.example.com \
  --target-username user --target-password pass

# 使用本地 Docker（无需沙箱）
rc image mirror nginx:latest --mode local \
  --target-registry registry.example.com \
  --target-username user --target-password pass

# 通过沙箱转储镜像（dump）
rc image dump nginx:latest python:3.11 --concurrency 2

# 管理转储任务（task）
rc image task list                  # 列出所有任务
rc image task status <task-id> -v   # 查看任务状态（含每条镜像详情）
rc image task resume <task-id>      # 恢复失败任务
rc image task delete <task-id>      # 删除任务
```

详细参数见 [references/agent.md](references/agent.md)、[references/experiment.md](references/experiment.md) 和 [references/image.md](references/image.md)。

---

## 全局选项

| 选项 | 说明 |
|------|------|
| `--verbose, -v` | 日志级别（-v: warning, -vv: info, -vvv: debug） |
| `--base-url <url>` | 服务端地址（默认 http://xrl.alibaba-inc.com） |
| `--api-key <key>` | API 密钥 |
| `--cluster <id>` | 集群标识 |
| `-H, --extra-header` | 额外 HTTP 请求头（格式：`Key=Value`） |
