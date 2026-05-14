# 安装 Rock Agents 技能

Rock Agents 提供适用于多种 AI Agent 工具的技能（Skills），支持 Claude Code、Cursor、Copilot、Codex、OpenCode、Windsurf 等平台。

## 方式一：Skills CLI 安装（推荐）

使用 [Vercel Labs Skills](https://github.com/vercel-labs/skills) 一键安装：

```bash
# 列出可用技能
npx skills add xdlkc/rock-skills --list

# 全局安装所有技能到所有支持的 Agent（推荐）
npx skills add xdlkc/rock-skills --all -g

# 安装到指定 Agent
npx skills add xdlkc/rock-skills -a claude-code -g
npx skills add xdlkc/rock-skills -a cursor -g
npx skills add xdlkc/rock-skills -a windsurf -g
npx skills add xdlkc/rock-skills -a opencode -g
npx skills add xdlkc/rock-skills -a codex -g

# 安装指定技能
npx skills add xdlkc/rock-skills --skill rock-cli -g
npx skills add xdlkc/rock-skills --skill rock-debug -g
npx skills add xdlkc/rock-skills --skill rock-agent-debug -g

# 非交互式安装（适合脚本/CI）
npx skills add xdlkc/rock-skills --all -g -y
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

## 方式二：手动复制

克隆仓库后手动复制技能文件到对应工具的技能目录：

```bash
git clone git@github.com:xdlkc/rock-skills.git ~/Code/rock-skills
```

### 各工具技能目录

| 工具 | 技能目录 |
|------|----------|
| Claude Code | `~/.claude/skills/` |
| Cursor | `~/.cursor/skills/` |
| Windsurf | `~/.codeium/windsurf/skills/` |
| Codex | `~/.codex/skills/` |
| OpenCode | `~/.opencode/skills/` |

复制示例：

```bash
# Claude Code
cp -r ~/Code/rock-skills/skills/rock-cli ~/.claude/skills/
cp -r ~/Code/rock-skills/skills/rock-debug ~/.claude/skills/
cp -r ~/Code/rock-skills/skills/rock-agent-debug ~/.claude/skills/

# Cursor
cp -r ~/Code/rock-skills/skills/rock-cli ~/.cursor/skills/
```

## 可用技能

| 技能 | 说明 |
|------|------|
| `rock-cli` | ROCK CLI 使用指南，涵盖沙箱管理、文件传输、交互式开发、Agent 评估等 |
| `rock-debug` | 沙箱排查工具，通过日志搜索、实时追踪、日志下载等方式定位沙箱问题 |
| `rock-agent-debug` | 排查 ROCK 沙箱中 Harbor Job 和 Bash Job 的状态与问题 |

## 验证安装

启动对应工具，检查技能列表：

- **Claude Code**: `/skills list`
- **Cursor**: Skills 面板或命令面板
- **其他工具**: 参考各工具文档

## 更新

```bash
# 使用 CLI 更新
npx skills update rock-cli
npx skills update rock-debug
npx skills update rock-agent-debug

# 或重新添加
npx skills add xdlkc/rock-skills --all -g -y
```

## 卸载

```bash
npx skills remove rock-cli
npx skills remove rock-debug
npx skills remove rock-agent-debug
```

或手动删除技能目录：

```bash
rm -rf ~/.claude/skills/rock-cli
rm -rf ~/.claude/skills/rock-debug
rm -rf ~/.claude/skills/rock-agent-debug
```
