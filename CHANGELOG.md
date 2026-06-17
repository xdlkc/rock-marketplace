# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [1.4.0] - 2026-06-17

### Added
- **rock-eval**: upgrade agent team pipeline to v2 — 7 roles (Lead / OracleChecker / NopChecker / Runner / Monitor / Diagnostician / Operator), parallel pipeline across 4 phases, Lead enforced as zero-execution coordinator, Operator loop for stop→destroy→retune→rerun cycles
- **rock-eval**: alignment baseline support — optional pre-run step to collect reference scores (leaderboard/paper/user-provided), config cross-check against official parameters, per-task `baselines/<name>.json` file for Diagnostician gap analysis

### Changed
- rock-eval: team-orchestration runbook rewritten for v2 (replaces v1 4-role serial design)
- rock-eval: SKILL.md decision tree updated with v2 pipeline and alignment scenario entries
- rock-eval: Diagnostician prompt gains alignment mode variant (actual vs expected comparison)

## [1.3.2] - 2026-06-17

### Added
- **rock-eval** skill: agent team orchestration for large regressions — coordinate Runner (background run/retry), Reporter (report/sync), and Diagnostician (failure deep-dive) subagents so the main context only holds conclusions, not raw logs/trajectories. Runbook at `references/team-orchestration.md`; design rationale at `docs/superpowers/specs/2026-06-17-rock-eval-agent-team-design.md`

### Changed
- Align `.claude-plugin/marketplace.json` descriptions with registry/plugin.json (previously stale — missing 评测/反馈 skills)

## [1.3.1] - 2026-06-17

### Changed
- rock-eval: clarify that `regression.py` must be run in place via its absolute path — no longer copied into the user's working directory; also clarifies that output (`results/`/`logs/`/`configs/`) is written relative to the invocation directory

## [1.3.0] - 2026-06-17

### Added
- **rock-eval** skill: configuration persistence — every `run`/`retry` auto-snapshots the full config to `configs/<experiment-id>.json`; new `--save-config <path>` saves to a custom template, `--from-config <path>` replays from JSON with CLI flags overriding

### Fixed
- rock-eval: window semantics — `--window-size` is now a true global concurrency cap (sliding window: one task finishes, the next starts immediately), eliminating the old batch-barrier wait where the next batch only began after the whole current batch finished. `--concurrency` kept as a compat alias (smaller value wins when both given)

## [1.2.0] - 2026-06-15

### Added
- **rock-feedback** skill: file skill-improvement issues/PRs against rock-* skills
- **rock-eval** skill: batch regression evaluation with task dispatch, result reports (text/HTML), status sync, failure diagnosis, and targeted reruns

### Changed
- Unified all skill descriptions to capability-first style
- rock-eval: query agent/bench live, add oracle/nop env check, clarify optional model and concurrency cap

## [1.1.0] - 2026-06-07

### Changed
- rock-cli: add image mirror/dump/task command docs
- rock-agent-debug: support job analysis via experiment id + job id
- rock-cli: add agent view/fs and experiment commands

## [1.0.0] - 2026-05-14

### Added
- **rock-debug** skill: expand to full sandbox troubleshooting guide with history, replay, diagnostic principles, cluster log sources, and scenario playbooks

### Changed
- Merge 3 plugins into single "rock" plugin with 3 skills (rock-cli, rock-debug, rock-agent-debug)
- Rename marketplace to rock-marketplace
- Migrate rock-cli and restructure plugins under marketplace "rock"

### Fixed
- Add required hooks field to hooks.json

## [0.3.0] - 2026-04-20

### Changed
- Rename skill to rock-agent-debug, add Bash Job support
- Rename plugin to rock-agent, bump to v1.3.0
- Add installation guide for `npx skills add`

## [0.2.0] - 2026-04-13

### Added
- Marketplace support via `.claude-plugin/marketplace.json`

### Changed
- Rename harbor-tools to rock-agent-harbor, merge skills into single skill

### Fixed
- Update plugin.json author format and remove invalid skills field

## [0.1.0] - 2026-04-12

### Added
- Initial release with harbor-tools plugin
- rock-agent-sdk skill for ROCK Agent SDK usage
