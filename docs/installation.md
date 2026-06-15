# 安装 Rock Skills

Rock Marketplace 提供适用于多种 AI Agent 工具的技能（Skills），支持 Claude Code、Cursor、Copilot、Codex、OpenCode、Windsurf 等平台。

## 方式一：Claude Code Plugin Marketplace（推荐）

一次安装全部技能：

```
/plugin marketplace add xdlkc/rock-marketplace
/plugin install rock@rock-marketplace
```

## 方式二：Skills CLI 安装

使用 [Vercel Labs Skills](https://github.com/vercel-labs/skills) 安装：

```bash
# 列出可用技能
npx skills add xdlkc/rock-marketplace --list

# 全局安装所有技能到所有支持的 Agent（推荐）
npx skills add xdlkc/rock-marketplace --all -g

# 安装到指定 Agent
npx skills add xdlkc/rock-marketplace -a claude-code -g
npx skills add xdlkc/rock-marketplace -a cursor -g

# 安装指定技能
npx skills add xdlkc/rock-marketplace --skill rock-cli -g

# 非交互式安装（适合脚本/CI）
npx skills add xdlkc/rock-marketplace --all -g -y
```

> **注意**：不加 `-g` 会安装到当前项目的 `.agents/skills/` 下，仅当前项目可用。加 `-g`（`--global`）才会安装到全局 `~/.agents/skills/`，所有项目都能使用。

### 支持的 Agent

| Agent | 标识符 |
|-------|--------|
| Claude Code | `claude-code` |
| Cursor | `cursor` |
| Windsurf | `windsurf` |
| OpenCode | `opencode` |
| Codex | `codex` |
| GitHub Copilot | `github-copilot` |
| Cline | `cline` |
| Goose | `goose` |
| Replit | `replit` |
| Kimi CLI | `kimi-cli` |
| Qwen Code | `qwen-code` |

## 方式三：手动复制

```bash
git clone git@github.com:xdlkc/rock-marketplace.git ~/Code/rock-marketplace
```

复制示例：

```bash
# Claude Code
cp -r ~/Code/rock-marketplace/skills/rock-cli ~/.claude/skills/
cp -r ~/Code/rock-marketplace/skills/rock-debug ~/.claude/skills/
cp -r ~/Code/rock-marketplace/skills/rock-agent-debug ~/.claude/skills/
```

## 包含技能

| 技能 | 说明 |
|------|------|
| `rock-cli` | ROCK CLI 使用指南，涵盖沙箱管理、文件传输、交互式开发、Agent 评估等 |
| `rock-debug` | 沙箱排查工具，按存活状态分流，支持日志搜索、exec 调试、history 回溯、replay 复现 |
| `rock-agent-debug` | Agent Job 排查，支持 Harbor Job 和 Bash Job 的状态查询、日志分析、Reward 查看 |
| `rock-eval` | 全量回归评测，支持批量任务派发、结果报告（文本/HTML）、状态同步、失败诊断、定向重跑 |
| `rock-feedback` | Skill 反馈工具，把对 rock-* 技能的 bug/建议整理成结构化 GitHub Issue 或 PR 并提交 |

## 验证安装

- **Claude Code**: `/skills list`
- **Cursor**: Skills 面板或命令面板

## 更新

```bash
# Skills CLI
npx skills add xdlkc/rock-marketplace --all -g -y

# Plugin Marketplace（自动更新）
/plugin update rock@rock-marketplace
```
