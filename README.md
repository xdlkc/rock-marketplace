# rock-marketplace

ROCK 平台 AI Agent 技能插件库，为 Claude Code 等 AI 工具提供针对 ROCK 平台的专属技能。

**ROCK (Reinforcement Open Construction Kit)** 是阿里巴巴开发的沙箱环境管理框架，专为 Agentic 强化学习场景设计。**Harbor** 是运行在 ROCK 沙箱中的 Agent Benchmark 评测框架。

## 结构

```
rock-marketplace/
├── skills/                             # Skills 目录（兼容 npx skills add）
│   ├── rock-cli ->                     # 软链到 plugins
│   ├── rock-debug ->                   # 软链到 plugins
│   ├── rock-agent-debug ->             # 软链到 plugins
│   ├── rock-eval ->                    # 软链到 plugins
│   └── rock-feedback ->                # 软链到 plugins
├── plugins/
│   └── rock/                           # 统一插件
│       ├── plugin.json
│       └── skills/
│           ├── rock-cli/               # CLI 使用指南
│           ├── rock-debug/             # 沙箱排查工具
│           ├── rock-agent-debug/       # Agent Job 排查
│           ├── rock-eval/              # 全量回归评测
│           └── rock-feedback/          # Skill 反馈工具
├── marketplace/
│   └── registry.json
└── docs/
    ├── installation.md
    └── plugin-spec.md
```

## 安装

详见 [安装指南](docs/installation.md)。

**快速安装（支持 Claude Code、Cursor、Windsurf、Codex、OpenCode 等）：**

```bash
npx skills add xdlkc/rock-marketplace --all -g
```

**Claude Code 用户可通过 Plugin Marketplace 安装（一次安装全部技能）：**

```
/plugin marketplace add xdlkc/rock-marketplace
/plugin install rock@rock-marketplace
```

## 包含技能

| 技能 | 说明 |
|------|------|
| `rock-cli` | ROCK CLI 使用指南，涵盖沙箱管理、文件传输、交互式开发、Agent 评估等 |
| `rock-debug` | 沙箱排查工具，按存活状态分流，支持日志搜索、exec 调试、history 回溯、replay 复现 |
| `rock-agent-debug` | Agent Job 排查，支持 Harbor Job 和 Bash Job 的状态查询、日志分析、Reward 查看 |
| `rock-eval` | 全量回归评测，支持批量任务派发、结果报告（文本/HTML）、状态同步、失败诊断、定向重跑 |
| `rock-feedback` | Skill 反馈工具，把对 rock-* 技能的 bug/建议整理成结构化 GitHub Issue 或 PR 并提交 |

## 开发

参考 [插件规范](docs/plugin-spec.md) 贡献新技能。
