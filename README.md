# rock-marketplace

English | [简体中文](./README.zh-CN.md)

Unified AI agent plugin marketplace and skill bundle for the **ROCK** platform and **Harbor** agent benchmark framework (supporting Claude Code, Cursor, Windsurf, Codex, OpenCode, and other skill-compatible coding agents).

- **ROCK (Reinforcement Open Construction Kit)** is Alibaba's sandbox environment management framework built for agentic reinforcement learning and coding-agent evaluation.
- **Harbor** is the agent benchmark evaluation framework executed inside ROCK sandboxes.

> **Language note**: The skill prompts (`SKILL.md`), reference guides (`references/*.md`), [`docs/installation.md`](./docs/installation.md), and [`docs/plugin-spec.md`](./docs/plugin-spec.md) in this repository are written primarily in Simplified Chinese alongside CLI commands and JSON schemas.

## ROCK Skill Ecosystem

Use this table to distinguish the three `xdlkc` ROCK skill repositories:

| Repository | Scope & Included Skills | Packaging & Install Path | Best For |
|---|---|---|---|
| **[`rock-marketplace`](https://github.com/xdlkc/rock-marketplace)** *(this repo)* | Unified `rock` plugin (`v1.4.7`): `rock-cli` (v2.7), `rock-debug`, `rock-agent-debug` (remote + in-sandbox), `rock-eval`, `rock-feedback` | `.claude-plugin/marketplace.json` (`/plugin install rock@rock-marketplace`) & `skills/` symlinks (`npx skills add`) | Most users: full ROCK CLI v2.7, sandbox diagnostics, remote/sandbox job debugging, and batch Harbor regression evaluation |
| [`rock-agents`](https://github.com/xdlkc/rock-agents) | Two plugins: `rock-agent-sdk` (`v1.0.0`: Python `rock.sdk.agent` & `rock_agent_config.yaml`) and `rock-agent` (`v1.3.0`: in-sandbox `rock-agent-debug`) | `.claude-plugin/marketplace.json` (`/plugin install rock-agent-sdk@rock-agents` & `rock-agent@rock-agents`) & `skills/` symlinks (`npx skills add`) | Developers writing Python SDK / YAML benchmark integrations (`rock-agent-sdk`, not included in `rock-marketplace`) |
| [`rock-cli-skills`](https://github.com/xdlkc/rock-cli-skills) | Standalone `rock-cli` skill (`SKILL.md` + `references/sandbox.md`) covering core sandbox lifecycle, `exec`, `upload`/`download`, `attach`, `log`, `history`, `replay` | Root `SKILL.md` (`npx skills add xdlkc/rock-cli-skills` or manual copy; no `.claude-plugin/` wrapper) | Minimal single-skill setup focused solely on `rockcli` sandbox operations |

## Included Skills (`rock` plugin v1.4.7)

All five skills live inside the single [`rock`](./plugins/rock/plugin.json) plugin and are symlinked under `skills/` for `npx skills add`:

| Skill | Summary | Source |
|---|---|---|
| `rock-cli` | ROCK CLI (`rockcli` / `rc`) v2.7 guide: auth, sandboxes (`start`/`exec`/`attach`/`upload`/`download`/`replay`), Windows sandboxes, `agent run/view/fs`, `expr`, `image` mirror/build, and `datasets` | [`SKILL.md`](./plugins/rock/skills/rock-cli/SKILL.md) |
| `rock-debug` | Read-only sandbox troubleshooting branched by lifecycle state (`alive` vs `stopped`), covering cluster logs, `command.log`/`rocklet.log`/`access.log`, `history`, `replay`, API failure root-cause, and disk-growth playbooks | [`SKILL.md`](./plugins/rock/skills/rock-debug/SKILL.md) |
| `rock-agent-debug` | Harbor Job and Bash Job diagnostics via both remote queries (`rc agent view`, `rc agent fs`) and in-sandbox checks (`rc sandbox <id> exec`), producing structured Markdown reports | [`SKILL.md`](./plugins/rock/skills/rock-agent-debug/SKILL.md) |
| `rock-eval` | End-to-end batch regression evaluation (`scripts/regression.py`, `fetch-overview.py`, `live-score.py`): task dispatch with sliding-window concurrency, config persistence, HTML/JSON/text reports, alignment baselines, failure taxonomy, and 7-role Agent Team orchestration (legacy v2 & TeamCreate) | [`SKILL.md`](./plugins/rock/skills/rock-eval/SKILL.md) |
| `rock-feedback` | Structured bug report and improvement workflow for filing GitHub Issues or PRs against `xdlkc/rock-marketplace` | [`SKILL.md`](./plugins/rock/skills/rock-feedback/SKILL.md) |

## Installation

### Option 1: Claude Code Plugin Marketplace (Installs All 5 Skills)

```text
/plugin marketplace add xdlkc/rock-marketplace
/plugin install rock@rock-marketplace
```

To update later:

```text
/plugin update rock@rock-marketplace
```

### Option 2: Vercel Labs `skills` CLI (Multi-Agent)

Works across Claude Code, Cursor, Windsurf, Codex, OpenCode, GitHub Copilot, Cline, Goose, Replit, Kimi CLI, and Qwen Code:

```bash
# List available skills
npx skills add xdlkc/rock-marketplace --list

# Install all skills globally
npx skills add xdlkc/rock-marketplace --all -g

# Install a single skill or target a specific agent
npx skills add xdlkc/rock-marketplace --skill rock-eval -g
npx skills add xdlkc/rock-marketplace -a claude-code -g
```

### Option 3: Manual Clone

```bash
git clone https://github.com/xdlkc/rock-marketplace.git
cp -r rock-marketplace/plugins/rock/skills/rock-cli ~/.claude/skills/
```

See [`docs/installation.md`](./docs/installation.md) (in Chinese) for full agent identifiers and installation details.

## Repository Structure

```text
rock-marketplace/
├── .claude-plugin/
│   └── marketplace.json            # Claude Code /plugin marketplace manifest
├── marketplace/
│   └── registry.json               # Marketplace registry (version 1.4.7, skills index)
├── plugins/
│   └── rock/
│       ├── plugin.json             # Plugin metadata (name: rock, version: 1.4.7)
│       ├── hooks/hooks.json        # Hooks manifest
│       └── skills/
│           ├── rock-cli/           # SKILL.md + references/{agent,datasets,experiment,image,sandbox}.md
│           ├── rock-debug/         # SKILL.md + references/log.md
│           ├── rock-agent-debug/   # SKILL.md
│           ├── rock-eval/          # SKILL.md + scripts/*.py + references/*
│           └── rock-feedback/      # SKILL.md
├── skills/                         # Top-level symlinks -> ../plugins/rock/skills/* (for npx skills add)
├── docs/
│   ├── installation.md             # Detailed installation guide
│   ├── plugin-spec.md              # Plugin and SKILL.md conventions
│   └── superpowers/                # Design specs and implementation plans for rock-eval
├── .claude/skills/
│   └── rock-plugin-release/        # Repo maintainer skill + scripts/check_consistency.py
└── CHANGELOG.md                    # Release history
```

## Contributing & Consistency Checks

Follow [`docs/plugin-spec.md`](./docs/plugin-spec.md) when adding or updating skills. Any change to skills or metadata must keep `.claude-plugin/marketplace.json`, `marketplace/registry.json`, `plugins/rock/plugin.json`, `skills/` symlinks, and `README.md` in sync—verify with:

```bash
python3 .claude/skills/rock-plugin-release/scripts/check_consistency.py
```

See [`CHANGELOG.md`](./CHANGELOG.md) for release history.
