# rock-marketplace

[English](./README.md) | 简体中文

面向 **ROCK** 平台与 **Harbor** 评测框架的统一 AI Agent 插件市场与技能合集（支持 Claude Code、Cursor、Windsurf、Codex、OpenCode 等工具）。

- **ROCK (Reinforcement Open Construction Kit)**：阿里巴巴开发的沙箱环境管理框架，专为 Agentic 强化学习与 Coding Agent 评测场景设计。
- **Harbor**：运行在 ROCK 沙箱中的 Agent Benchmark 评测框架。

## ROCK Skill 生态对比

`xdlkc` 下共有三个与 ROCK 相关的技能仓库，定位与包含范围如下：

| 仓库 | 定位与包含技能 | 分发与安装方式 | 适用人群 |
|---|---|---|---|
| **[`rock-marketplace`](https://github.com/xdlkc/rock-marketplace)** *(本仓库)* | 统一 `rock` 插件（`v1.4.7`）：`rock-cli`（v2.7）、`rock-debug`、`rock-agent-debug`（支持远程查询 + 沙箱内排查）、`rock-eval`、`rock-feedback` | `.claude-plugin/marketplace.json`（`/plugin install rock@rock-marketplace`）及顶层 `skills/` 软链（`npx skills add`） | **绝大多数用户**：需要完整 ROCK CLI v2.7、沙箱故障排查、Job 调试与 Harbor 全量回归评测 |
| [`rock-agents`](https://github.com/xdlkc/rock-agents) | 两个独立插件：`rock-agent-sdk`（`v1.0.0`：Python `rock.sdk.agent` 与 `rock_agent_config.yaml`）与 `rock-agent`（`v1.3.0`：沙箱内 `rock-agent-debug`） | `.claude-plugin/marketplace.json`（`/plugin install rock-agent-sdk@rock-agents` 与 `rock-agent@rock-agents`）及顶层 `skills/` 软链（`npx skills add`） | 需要编写 Python SDK / YAML 评测配置（`rock-agent-sdk` 仅在此仓库）或单独安装 `rock-agent` 的开发者 |
| [`rock-cli-skills`](https://github.com/xdlkc/rock-cli-skills) | 单技能独立包（`SKILL.md` + `references/sandbox.md`），聚焦 `rockcli` 核心沙箱生命周期、`exec`、上传下载、`attach`、`log`、`history`、`replay` | 根目录 `SKILL.md`（`npx skills add xdlkc/rock-cli-skills` 或手动复制；无 `.claude-plugin/` 包装） | 仅需 `rockcli` 沙箱基础操作、希望最小化单技能安装的用户 |

## 包含技能（`rock` 插件 v1.4.7）

全部五个技能统一封装在 [`rock`](./plugins/rock/plugin.json) 插件中，并在顶层 `skills/` 下提供软链以兼容 `npx skills add`：

| 技能 | 说明 | 源文件 |
|---|---|---|
| `rock-cli` | ROCK CLI（`rockcli` / `rc`）v2.7 使用指南，涵盖认证、沙箱启停与 `exec`/`attach`/`upload`/`download`/`replay`、Windows 沙箱、`agent run/view/fs`、`expr`、`image` 镜像转储/构建、以及 `datasets` 管理 | [`SKILL.md`](./plugins/rock/skills/rock-cli/SKILL.md) |
| `rock-debug` | 只读沙箱排查指南，按 `alive` / `stopped` 状态分流，涵盖集群日志、`command.log`/`rocklet.log`/`access.log`、`history`、`replay`、接口失败根因与磁盘暴涨排查流程 | [`SKILL.md`](./plugins/rock/skills/rock-debug/SKILL.md) |
| `rock-agent-debug` | Harbor Job 与 Bash Job 排查工具，同时支持远程查询（`rc agent view` / `rc agent fs`）与沙箱内排查（`rc sandbox <id> exec`），输出落盘诊断报告 | [`SKILL.md`](./plugins/rock/skills/rock-agent-debug/SKILL.md) |
| `rock-eval` | 全量回归评测套件（`scripts/regression.py`、`fetch-overview.py`、`live-score.py`）：滑动窗口并发派发、配置持久化、HTML/JSON/文本报告、对齐基线对比、失败分类体系与 7 角色 Agent Team 编排（legacy v2 与 TeamCreate） | [`SKILL.md`](./plugins/rock/skills/rock-eval/SKILL.md) |
| `rock-feedback` | Skill 反馈工具，将对 `rock-*` 技能的问题或改进建议整理为结构化 GitHub Issue 或 PR 并提交至 `xdlkc/rock-marketplace` | [`SKILL.md`](./plugins/rock/skills/rock-feedback/SKILL.md) |

## 安装

### 方式一：Claude Code Plugin Marketplace（一次安装全部 5 个技能）

```text
/plugin marketplace add xdlkc/rock-marketplace
/plugin install rock@rock-marketplace
```

后续升级：

```text
/plugin update rock@rock-marketplace
```

### 方式二：Skills CLI（跨工具全局或单技能安装）

支持 Claude Code、Cursor、Windsurf、Codex、OpenCode、GitHub Copilot、Cline、Goose、Replit、Kimi CLI 与 Qwen Code：

```bash
# 查看可用技能
npx skills add xdlkc/rock-marketplace --list

# 全局安装全部技能
npx skills add xdlkc/rock-marketplace --all -g

# 仅安装指定技能，或指定目标 Agent
npx skills add xdlkc/rock-marketplace --skill rock-eval -g
npx skills add xdlkc/rock-marketplace -a claude-code -g
```

### 方式三：手动克隆复制

```bash
git clone https://github.com/xdlkc/rock-marketplace.git
cp -r rock-marketplace/plugins/rock/skills/rock-cli ~/.claude/skills/
```

完整安装说明与各工具标识符见 [`docs/installation.md`](./docs/installation.md)。

## 仓库结构

```text
rock-marketplace/
├── .claude-plugin/
│   └── marketplace.json            # Claude Code /plugin marketplace 清单
├── marketplace/
│   └── registry.json               # Marketplace 注册表（v1.4.7 与技能索引）
├── plugins/
│   └── rock/
│       ├── plugin.json             # 插件元数据（name: rock, version: 1.4.7）
│       ├── hooks/hooks.json        # Hooks 配置
│       └── skills/
│           ├── rock-cli/           # SKILL.md + references/{agent,datasets,experiment,image,sandbox}.md
│           ├── rock-debug/         # SKILL.md + references/log.md
│           ├── rock-agent-debug/   # SKILL.md
│           ├── rock-eval/          # SKILL.md + scripts/*.py + references/*
│           └── rock-feedback/      # SKILL.md
├── skills/                         # 顶层软链 -> ../plugins/rock/skills/*（兼容 npx skills add）
├── docs/
│   ├── installation.md             # 详细安装指南
│   ├── plugin-spec.md              # 插件与 SKILL.md 规范
│   └── superpowers/                # rock-eval 演进设计与实施计划
├── .claude/skills/
│   └── rock-plugin-release/        # 仓库维护与发布校验脚本 check_consistency.py
└── CHANGELOG.md                    # 版本变更记录
```

## 维护与一致性校验

新增或修改技能请遵循 [`docs/plugin-spec.md`](./docs/plugin-spec.md)。任何技能或元数据变更都应同步 `.claude-plugin/marketplace.json`、`marketplace/registry.json`、`plugins/rock/plugin.json`、`skills/` 软链与 `README.md`，修改后运行一致性检查：

```bash
python3 .claude/skills/rock-plugin-release/scripts/check_consistency.py
```

历史变更见 [`CHANGELOG.md`](./CHANGELOG.md)。
