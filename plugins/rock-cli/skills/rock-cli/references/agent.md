# agent 命令详细参数

AI Agent 评估任务管理，通过 Python rock-sdk 执行评估任务。需要 Python >= 3.10。

## run - 运行评估任务

```bash
rockcli agent run -c <config.yaml> [选项]
```

| 参数 | 说明 |
|------|------|
| `-c, --config <path>` | JobConfig YAML 配置文件路径（必填） |
| `-t, --task <name>` | 指定运行的任务名称（覆盖配置文件中的 task_names） |
| `--pre` | 使用预发环境的数据集和结果上报 |

```bash
# 从配置文件运行评估任务
rockcli agent run -c job.yaml

# 运行指定的单个任务
rockcli agent run -c job.yaml -t astropy__astropy-7606

# 使用预发环境运行评估任务
rockcli agent run -c job.yaml --pre
```
