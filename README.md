# rock-agents

ROCK 平台 AI Agent 技能插件库，为 Claude Code 等 AI 工具提供针对 ROCK 平台的专属技能。

**ROCK (Reinforcement Open Construction Kit)** 是阿里巴巴开发的沙箱环境管理框架，专为 Agentic 强化学习场景设计。**Harbor** 是运行在 ROCK 沙箱中的 Agent Benchmark 评测框架。

## 结构

```
rock-agents/
├── plugins/                    # 插件目录，每个子目录是一个独立插件
│   └── harbor-tools/           # ROCK Harbor Agent 评测工具集
│       ├── plugin.json         # 插件元数据
│       ├── hooks/              # 钩子配置
│       │   └── hooks.json
│       └── skills/             # 技能集合
│           ├── rock-agent-sdk/     # Agent SDK 开发指南
│           ├── harbor-sandbox-status/ # 沙箱状态查询
│           └── harbor-debug/        # Benchmark 调试
├── marketplace/                # Marketplace 索引
│   └── registry.json           # 已发布插件注册表
└── docs/                       # 文档
    └── plugin-spec.md          # 插件规范
```

## 安装插件

在 Claude Code 中通过 marketplace 安装：

```
/plugin marketplace add xdlkc/rock-agents
/plugin install harbor-tools@rock-agents
```

或手动安装（将插件目录软链到 `~/.claude/plugins/`）：

```bash
ln -s ~/Code/rock-agents/plugins/harbor-tools ~/.claude/plugins/harbor-tools
```

## 开发插件

参考 [插件规范](docs/plugin-spec.md) 创建新插件。

每个插件包含：
- `plugin.json` — 插件元数据（名称、版本、描述、作者）
- `hooks/hooks.json` — 钩子配置（可选）
- `skills/<skill-name>/SKILL.md` — 技能文件

## 已有插件

| 插件 | 描述 | 技能数 |
|------|------|--------|
| `harbor-tools` | ROCK Harbor Agent 评测工具集 | 3 |

### harbor-tools 技能列表

| 技能 | 说明 |
|------|------|
| `rock-agent-sdk` | 辅助开发者基于 ROCK Agent SDK 开发 Agent Benchmark 评测 |
| `harbor-sandbox-status` | 查询 ROCK 沙箱中 Harbor 任务执行状态 |
| `harbor-debug` | Harbor Benchmark 运行问题排查和诊断 |
