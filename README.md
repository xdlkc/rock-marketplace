# rock-skills

ROCK 平台 AI Agent 技能插件库，为 Claude Code 等 AI 工具提供针对 ROCK 平台的专属技能。

**ROCK (Reinforcement Open Construction Kit)** 是阿里巴巴开发的沙箱环境管理框架，专为 Agentic 强化学习场景设计。**Harbor** 是运行在 ROCK 沙箱中的 Agent Benchmark 评测框架。

## 结构

```
rock-skills/
├── skills/                             # Skills 目录（兼容 npx skills add）
│   ├── rock-cli ->                     # 软链到 plugins
│   ├── rock-debug ->                   # 软链到 plugins
│   └── rock-agent-debug ->             # 软链到 plugins
├── plugins/                            # Claude Code Plugin 目录
│   ├── rock-cli/                       # ROCK CLI 使用指南
│   │   ├── plugin.json
│   │   └── skills/rock-cli/
│   ├── rock-debug/                     # 沙箱排查工具
│   │   ├── plugin.json
│   │   └── skills/rock-debug/
│   └── rock-agent-debug/               # Agent Job 排查
│       ├── plugin.json
│       └── skills/rock-agent-debug/
├── marketplace/                        # Marketplace 索引
│   └── registry.json
└── docs/
    ├── installation.md                 # 安装指南
    └── plugin-spec.md                  # 插件规范
```

## 安装技能

详见 [安装指南](docs/installation.md)。

**快速安装（支持 Claude Code、Cursor、Windsurf、Codex、OpenCode 等）：**

```bash
npx skills add xdlkc/rock-skills --all
```

**Claude Code 用户可通过 Plugin Marketplace 安装：**

```
/plugin marketplace add xdlkc/rock-skills
/plugin install rock-cli@rock
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
| `rock-cli` | ROCK CLI 使用指南 | 1 |
| `rock-debug` | 沙箱排查工具 | 1 |
| `rock-agent-debug` | Agent Job 排查 | 1 |

### 插件详情

**rock-cli**
| 技能 | 说明 |
|------|------|
| `rock-cli` | ROCK CLI 使用指南，涵盖沙箱管理、文件传输、交互式开发、Agent 评估等 |

**rock-debug**
| 技能 | 说明 |
|------|------|
| `rock-debug` | 通过日志搜索、实时追踪、日志下载等方式定位沙箱问题 |

**rock-agent-debug**
| 技能 | 说明 |
|------|------|
| `rock-agent-debug` | 查询和排查 ROCK 沙箱中 Harbor Job 和 Bash Job 的状态与问题 |
