# rockcli (rc) 命令速查

回归流程中常用的 `rc` 命令，可在排查问题或手动操作时直接使用。

> 全局选项 `--pre`（预发环境）、`--api-key <KEY>` 几乎所有命令都需要，下面示例中省略时表示使用默认值。

---

## 从 bench 反查数据集并获取 task 列表

当用户只给了 bench 名字（没给 dataset/split）时，**先从 bench template 反查它跑的是哪个
数据集**，再据此获取 task 列表：

```bash
# 1. 查 bench template 全量配置，看 datasets 字段
rc agent bench getconfig <BENCH> --raw
```

template 里的 `datasets` 字段形如：

```yaml
datasets:
  - registry:
      split: "test"            # ← split
    name: "alibaba/aone-bench-java100"   # ← 数据集名
    task_names:
      - ""                     # 空 → task 在数据集里，需用 rc datasets tasks 查
      # - "fix-git"            # 非空 → task_names 直接内嵌在 template 里
```

```bash
# 2. 用反查到的 dataset + split 获取 task 列表
rc datasets <NAME> tasks --split <SPLIT> --pre --api-key <KEY>
```

> **回退**：若该数据集不支持 `tasks` 子命令、或查不到任何 task，则改用 template `--raw`
> 输出里 `datasets[].task_names` 的内嵌列表作为 task 来源。
> harbor 类 bench（如 `harborframework/*`）template 必有 `datasets.name`，可稳定走第 1-2 步。

---

## 数据集管理 (`rc datasets`)

```bash
# 列出所有数据集
rc datasets list --pre --api-key <KEY>

# 查看数据集的 split 列表
rc datasets alibaba/aone-bench-java100 splits --pre --api-key <KEY>

# 查看某个 split 下的任务列表
rc datasets alibaba/aone-bench-java100 tasks --split delivery_0609-cn --pre --api-key <KEY>

# 查看某个任务的文件列表
rc datasets alibaba/aone-bench-java100 fs ls codereview-21491816 \
  --split delivery_0609-cn --pre --api-key <KEY>

# 查看任务文件内容
rc datasets alibaba/aone-bench-java100 fs cat codereview-21491816/problem_statement.md \
  --split delivery_0609-cn --pre --api-key <KEY>
```

---

## 单任务运行 (`rc agent run`)

```bash
# 运行单个任务
rc agent run --bench aone-bench --task codereview-21491816 \
  --agent claude-code --pre --api-key <KEY>

# 指定镜像、模型、环境变量
rc agent run --bench aone-bench --task codereview-21491816 \
  --agent mini-swe-agent \
  --image <IMAGE> --model glm-5.1 \
  --ee OPENAI_API_KEY=sk-xxx \
  --ee OPENAI_BASE_URL=https://... \
  --pre --api-key <KEY>

# Dry Run — 只生成配置不执行
rc agent run --bench aone-bench --task codereview-21491816 \
  --agent claude-code --dry-run --pre

# 异步模式 — 提交后立即退出
rc agent run --bench aone-bench --task codereview-21491816 \
  --agent claude-code --async --pre

# 启用陪跑助手
rc agent run --bench aone-bench --task codereview-21491816 \
  --agent swe-agent --with claude-code --pre

# 指定 CPU/内存规格
rc agent run --bench aone-bench --task codereview-21491816 \
  --agent claude-code --cpus 8 --memory 16 --pre

# 使用 YAML 配置文件
rc agent run --config job.yaml --task codereview-21491816

# 多任务并发
rc agent run --bench terminal-bench-2 --agent swe-agent \
  --tasks fix-git gcode-to-text regex-log --concurrency 2
```

### 查看可用 bench / agent（实时查询，不要写死）

支持的 bench 模板和 agent 随 rockcli 版本变化，**始终以实时查询为准**：

```bash
# 当前支持的 bench / agent（看输出里的"常用取值"段）
rc agent run --help

# 刷新 benchhub 模板列表
rc agent deps sync benchhub
```

两个语义稳定的 baseline agent（用途不随版本变）：

- `oracle` — 上界 baseline，提交正确答案，验证评分链路
- `nop` — 下界 baseline，不做操作，验证派发/环境链路

---

## 查看结果 (`rc agent view`)

```bash
# 列举所有实验
rc agent view -E --pre --api-key <KEY>

# 列举实验下的 Jobs
rc agent view -e <EXPERIMENT_ID> --pre --api-key <KEY>

# 分页查看（每页 50 条，从第 51 条开始）
rc agent view -e <EXPERIMENT_ID> --limit 50 --offset 50 --pre --api-key <KEY>

# 查看单个 Job 详情
rc agent view -j <JOB_NAME> -e <EXPERIMENT_ID> --pre --api-key <KEY>

# JSON 格式输出（供脚本解析）
rc agent view -j <JOB_NAME> -e <EXPERIMENT_ID> --pre -o json --api-key <KEY>

# 查看执行轨迹
rc agent view -j <JOB_NAME> -e <EXPERIMENT_ID> --trajectory --pre --api-key <KEY>
```

---

## 文件操作 (`rc agent fs`)

```bash
# 列出 Job 根目录文件
rc agent fs ls -e <EXPERIMENT_ID> -j <JOB_NAME> --pre --api-key <KEY>

# 按路径前缀列文件
rc agent fs ls codereview-21491816/agent \
  -e <EXPERIMENT_ID> -j <JOB_NAME> --pre

# 列出 Trial 文件（自动选择唯一 trial）
rc agent fs ls -e <EXPERIMENT_ID> -j <JOB_NAME> -t <TASK_NAME> --pre

# 查看远程日志
rc agent fs cat run.log -e <EXPERIMENT_ID> -j <JOB_NAME> --pre --api-key <KEY>

# 查看 Trial scope 日志
rc agent fs cat agent/log.txt \
  -e <EXPERIMENT_ID> -j <JOB_NAME> -t <TASK_NAME> --pre

# 下载文件到本地
rc agent fs download trajectory.json \
  -e <EXPERIMENT_ID> -j <JOB_NAME> -t <TASK_NAME> -o ./ --pre

# 下载到 stdout（pipe）
rc agent fs download trajectory.json \
  -e <EXPERIMENT_ID> -j <JOB_NAME> -t <TASK_NAME> -o - --pre

# 查看 Trial 产物和 manifest
rc agent fs artifacts -e <EXPERIMENT_ID> -j <JOB_NAME> -t <TASK_NAME> --pre --api-key <KEY>
```

---

## 实验管理 (`rc experiment` / `rc expr`)

```bash
# 查看实验沙箱总数和分布
rc expr <EXPERIMENT_ID> --pre --api-key <KEY>

# 查询实验下的沙箱列表
rc expr <EXPERIMENT_ID> sandboxes --pre --api-key <KEY>

# 查看所有状态的沙箱（包括已停止的）
rc expr <EXPERIMENT_ID> sandboxes \
  --status RUNNING,PENDING,STOPPED --pre --api-key <KEY>

# 批量停止实验下的沙箱（先 dry-run 确认）
rc expr <EXPERIMENT_ID> sandboxes stop --dry-run --pre --api-key <KEY>
rc expr <EXPERIMENT_ID> sandboxes stop --pre --api-key <KEY>

# 分页查询（每页 50）
rc expr <EXPERIMENT_ID> sandboxes --size 50 --page 2 --pre --api-key <KEY>
```

---

## Bench 模板 (`rc agent bench`)

```bash
# 列出所有可用的 bench 模板
rc agent bench list

# 查看 bench 的配置参数（环境变量等）
rc agent bench getconfig aone-bench
```

---

## 依赖管理 (`rc agent deps`)

```bash
# 同步 Agent 运行时依赖（benchhub 模板等）
rc agent deps sync benchhub
```

---

## 沙箱操作 (`rc sandbox`)

```bash
# 启动沙箱
rc sandbox start --image <IMAGE> --cluster <CLUSTER>

# 查看沙箱状态
rc sandbox <SANDBOX_ID> status

# 在沙箱中执行命令
rc sandbox <SANDBOX_ID> exec -- ls -la

# 连接到沙箱终端
rc sandbox <SANDBOX_ID> attach

# 搜索沙箱日志
rc sandbox <SANDBOX_ID> log search -k "error"
```
