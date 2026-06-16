# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

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
