---
name: rock-plugin-release
description: |
  维护和发布 rock-marketplace 这个 plugin 仓库时使用。当用户要新增 skill、删除 skill、更新 skill 内容、修改 plugin 的元数据（plugin.json/registry.json/marketplace.json）、调整 README、给 plugin 升版本号、或者任何会改变 plugin 行为/对外暴露面的仓库改动时，使用本 skill 确保六处关键位置保持一致并正确升版。
  具体触发场景：新增/删除/重命名一个 skill、修改 skill 的 SKILL.md 内容、改 plugin.json、改 marketplace/registry.json、改 README 中的技能列表或结构图、bump 版本号、发布 plugin、提到 marketplace/插件仓库/marketplace registry/semver 升版。当用户说"给 rock plugin 加个新技能""删除 xxx skill""更新插件版本""发布插件""registry 怎么改"时使用。即使没明说"plugin"，只要是对本仓库 plugins/ 或 marketplace/ 或顶层 skills/ 软链的改动，都适用。
---

# rock-plugin-release — plugin 仓库维护与发布

本 skill 用于维护 `rock-marketplace` 这个 plugin 仓库。这个仓库是一个**单 plugin（`rock`）+ 多 skill** 的结构，关键约束是：**任何会改变 plugin 行为或对外暴露面的改动，都必须同步到六处位置，并按 semver 升版**。漏改任何一处，就会导致已安装用户拿到的版本与 marketplace 声明的不一致，或某条安装路径（`npx skills add` / `/plugin install` / `/plugin marketplace add`）行为不一致——这种不一致很难被发现，却会真实地坑到使用者。

理解了这个"为什么"，下面的所有规则就都是顺理成章的了。

## 六处必须同步的位置

每次改动后，对照检查这六处是否一致：

| # | 位置 | 改什么 | 何时改 |
|---|------|--------|--------|
| 1 | `plugins/rock/skills/<skill>/` | skill 实际内容（SKILL.md + scripts/ + references/） | 新增/删除/更新 skill 时 |
| 2 | `skills/<skill>` | 顶层软链 → `../plugins/rock/skills/<skill>` | **仅新增 skill 时创建**；删除 skill 时移除 |
| 3 | `plugins/rock/plugin.json` | `version` + `description` | 每次会影响行为的改动 |
| 4 | `marketplace/registry.json` | `version` + `description` + `skills[]` + `updated_at` | 每次会影响行为的改动 |
| 5 | `.claude-plugin/marketplace.json` | 内层 plugin 的 `description`（+ 外层 marketplace description 若涉及） | description 变更时 |
| 6 | `README.md` | 结构图 + 「包含技能」表格 | skill 增删或 description 变更时 |

三条安装路径分别依赖不同的清单，所以必须都保持一致：

- **`npx skills add`** 只认顶层 `skills/` 软链（第 2 处）
- **`/plugin install`** 走 `plugins/` + `registry.json`（第 3、4 处）
- **`/plugin marketplace add`** 读 `.claude-plugin/marketplace.json`（第 5 处）

第 5 处尤其容易漏——它独立于 registry.json，含外层 marketplace 和内层 plugin **两个** description。历史上就出现过新增 skill 时只改了 registry 而漏改它，导致 marketplace 列表展示的描述落后于实际。校验脚本会按关键词检查它是否跟上。

## 一致性校验（必做）

本 skill 内置校验脚本，**任何改动前后都要跑一次**：

```bash
python3 .claude/skills/rock-plugin-release/scripts/check_consistency.py
```

它会检查：版本号是否在 plugin.json/registry.json 间一致、registry 的 skills 列表是否与实际目录一致、每个 SKILL.md 是否有合法 frontmatter、顶层软链是否齐全且指向正确、README 是否提到所有 skill、updated_at 格式。退出码 0=全部一致，1=有问题。

脚本只读不改，可以放心反复跑。**改动完成后必须看到"一致性检查通过"才能收工**——这一步是防止漏改的兜底。

## 版本号（semver）判断

升版由你（执行 skill 的 agent）根据改动类型**判断并建议**，但**最终版本号由用户确认**——不要擅自 bump。判断规则：

> **本仓库的简化规则（覆盖标准 semver）**：只有 **skill 列表发生增删**（新增 skill 或删除/重命名 skill）才升 `minor`；其余所有改动——skill 内部内容更新（含新增能力、修复）、文档/README/元数据/hooks 调整——一律升 `patch`。除非用户另有指示，不升 `major`。

| 改动类型 | 升级 | 例子 |
|---------|------|------|
| **新增 skill** | `minor` | 新增 `rock-eval` |
| **删除 / 重命名 skill** | `minor` | skill 列表变化即升 minor |
| **更新 skill 内容**（增强/修复/新增能力，不增删 skill） | `patch` | skill 内加 runbook、修 bug、加 agent team 编排 |
| **只改文档/README/元数据** | `patch` | 调整 description 文案、对齐 marketplace.json |
| **修改 hooks 行为** | `patch` | 除非用户要求更高 |

判断时把握一条原则：**skill 列表（`registry.json` 的 `skills[]` 与顶层软链）变没变？** 变了升 minor，没变升 patch。判断不清就按 patch 对待并请用户确认。

升版时**plugin.json 和 registry.json 必须同步**——两处的 `version` 要完全一致。当前仓库曾出现过 `plugin.json=1.0.0` 而 `registry.json=1.1.0` 的不一致（校验脚本正是为抓这类问题而生）。

## 典型操作流程

### 新增一个 skill（如 `rock-xxx`）

1. 创建 `plugins/rock/skills/rock-xxx/SKILL.md`（带合法 frontmatter：`name` 与目录名一致、`description` 写清触发场景）。
2. 创建顶层软链：`ln -s ../plugins/rock/skills/rock-xxx skills/rock-xxx`（在仓库根目录执行）。
3. `plugin.json`：`description` 若需体现新 skill 则更新；bump version（按上表，通常是 minor）。
4. `registry.json`：`skills` 数组加 `"rock-xxx"`；同步 version 与 description；更新 `updated_at`（用今天日期，格式 `YYYY-MM-DD`）。
5. `.claude-plugin/marketplace.json`：若 description 改了，内层 `rock` plugin 的 description（必要时还有外层 marketplace description）也要同步跟上。
6. `README.md`：结构图补一行软链 + 目录、技能表格补一行。
7. 跑校验脚本，确认通过。

### 删除一个 skill

1. 删除 `plugins/rock/skills/<skill>/` 目录。
2. 删除顶层软链 `skills/<skill>`。
3. `registry.json` 的 `skills` 数组移除该项；同步 version（删除 skill 列表变化，升 minor）；更新 `updated_at`。
4. `plugin.json` 同步 version、必要时改 description。
5. `.claude-plugin/marketplace.json`：若 description 改了，同步内层（必要时外层）description。
6. `README.md` 移除结构图与表格中的对应行。
7. 跑校验脚本。

### 更新 skill 内容（修复/增强，不增删）

1. 改 `plugins/rock/skills/<skill>/` 下的文件（软链自动跟上，无需动顶层 `skills/`）。
2. 升 patch（skill 列表未变），同步 `plugin.json` 与 `registry.json` 的 version；更新 `registry.json` 的 `updated_at`。
3. 若 description 实质性变化，同步四处 description：`plugin.json` / `registry.json` / `.claude-plugin/marketplace.json` 内层 / README 表格。
4. 跑校验脚本。

### 仅改元数据 / 文档

跑校验脚本即可，version 通常升 patch（或保持，看用户意愿）。

## updated_at 日期

`registry.json` 的 `updated_at` 在**任何影响 version 的改动时都要刷新为今天**。当前会话的"今天"请向用户确认或使用已知日期，不要臆造未来日期（校验脚本会把未来日期标为告警）。

## 收尾清单

每次改动提交前，对照确认：

- [ ] 校验脚本输出"一致性检查通过"
- [ ] `plugin.json` 与 `registry.json` 的 version 完全一致
- [ ] 若 version 变了，`registry.json` 的 `updated_at` 已刷新
- [ ] 新增/删除的 skill 在 registry `skills[]`、顶层软链、README 中一致
- [ ] 若 description 变了，`.claude-plugin/marketplace.json` 已同步（极易漏）
- [ ] 已向用户说明建议的版本号及理由并获得确认

按项目约定，提交信息格式为 `<type>(<scope>): <description>`，如 `feat(rock): add rock-xxx skill`。
