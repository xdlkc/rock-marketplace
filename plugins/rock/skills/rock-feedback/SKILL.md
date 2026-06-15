---
name: rock-feedback
description: 向 rock-marketplace 仓库提交 skill 改进反馈——把用户对某个 rock-* skill 的吐槽、bug、改进想法整理成结构化的 GitHub Issue 或 PR 并直接提交。当用户说"这个 skill 不好用/有 bug/应该改成…"、"给 xxx skill 提个 issue/PR"、"反馈一下这个技能的问题"，或在使用 rock-cli / rock-debug / rock-agent-debug / rock-eval 过程中表达了不满或建议时使用。
---

# Rock Feedback — 提交 Skill 改进反馈

把用户对 rock-* skills 的反馈整理成高质量的 GitHub Issue 或 PR，提交到本插件仓库 **`xdlkc/rock-marketplace`**。

反馈的价值取决于它有多具体、多可操作。你的核心工作不是机械转发用户的一句话，而是补全上下文（哪个 skill、哪个版本、什么场景、期望 vs 实际），让维护者拿到就能动手。

## 何时使用

- 用户对某个 skill 表达不满、困惑或建议改进
- 用户明确要求"提 issue / 提 PR / 反馈问题"
- 在使用 rock-cli / rock-debug / rock-agent-debug / rock-eval 时发现了 bug 或文档错误
- 用户描述了一个"skill 本该能做但没做好"的场景

## 目标仓库

固定为 `xdlkc/rock-marketplace`。Skills 位于 `plugins/rock/skills/<skill-name>/`。

## 决策树：Issue 还是 PR？

```
用户的反馈是什么性质？
│
├─ 模糊的不满 / bug 现象 / 改进想法，但没有具体改法 ──→ 提 Issue
│     例："rock-debug 的日志搜索经常输出太多" "希望支持 xxx"
│
├─ 有明确、可落地的改动方案（改某行文档、加个命令说明、修个错别字） ──→ 提 PR
│     例："rock-eval 文档里 retry 命令的参数写错了，应该是 --filter error"
│
└─ 不确定 ──→ 默认提 Issue（成本低、维护者可讨论后再改）
```

**优先 Issue**：除非用户明确想直接改代码、或改动小到一眼能写对，否则提 Issue。Issue 让维护者参与决策，避免提了个不被接受的 PR。

## 提交前必做：把反馈问清楚

低质量反馈对维护者毫无帮助。提交前确保收集到这些信息（缺的就问用户，或从当前会话/环境推断）：

1. **哪个 skill** — rock-cli / rock-debug / rock-agent-debug / rock-eval，还是别的
2. **版本** — 读 `plugins/rock/plugin.json` 的 `version`（若在本仓库），或问用户装的版本
3. **场景** — 用户当时在做什么、用了哪条命令/哪段指引
4. **期望 vs 实际** — 期望 skill 怎么表现，实际怎么表现
5. **可选** — 报错输出、复现步骤、用户设想的修复方向

> 不要追问到用户烦躁。会话里已能推断的（比如刚刚就在用 rock-eval 跑回归）直接用，只问真正缺失的关键项。

## 路径一：提交 Issue

### 1. 整理正文

用这个模板（按反馈类型裁剪，bug 用全部字段，建议类可省略复现步骤）：

```markdown
## 涉及 Skill
`<skill-name>` (version <x.y.z>)

## 问题 / 建议
<一句话说清核心>

## 场景
<用户在做什么，触发了什么>

## 期望表现
<应该怎样>

## 实际表现
<实际怎样；bug 附报错输出>

## 复现步骤（如适用）
1. ...
2. ...

## 可能的改进方向（可选）
<用户或你的设想>
```

### 2. 用 gh CLI 提交（优先）

先确认 gh 可用且已登录：

```bash
gh auth status
```

提交（标题简明、带 skill 前缀，便于维护者归类）：

```bash
gh issue create \
  --repo xdlkc/rock-marketplace \
  --title "[rock-debug] 日志搜索默认输出过多，建议加默认行数上限" \
  --body-file <(cat <<'EOF'
## 涉及 Skill
`rock-debug` (version 1.1.0)
... 正文 ...
EOF
)
```

提交成功后把返回的 issue 链接给用户。

### 3. 无 gh 时回退

若 `gh` 不存在或未登录，**不要中断**——把整理好的标题 + 正文展示给用户，并给出网页提交链接：

```
https://github.com/xdlkc/rock-marketplace/issues/new
```

告诉用户：复制上面的标题和正文，点链接粘贴即可。

## 路径二：提交 PR

仅在有明确、可落地改动时走这条路。流程：fork（如无权限）→ 分支 → 改 → 提 PR。

### 1. 确认改动范围

明确要改哪个文件、改什么。常见对象：
- `plugins/rock/skills/<skill>/SKILL.md` — skill 主指引
- `plugins/rock/skills/<skill>/references/*.md` — 附属参考文档
- `docs/` — 安装/规范文档

**改动要最小**：只动反馈相关的内容，不顺手重构、不改风格。遵循该 skill 现有的中文风格与结构。

### 2. 准备分支并改动

若工作区就是本仓库（`git remote -v` 指向 `xdlkc/rock-marketplace`）且有 push 权限：

```bash
git checkout -b fix/rock-debug-log-default-limit
# 用 Edit 工具改文件
```

无 push 权限时先 fork：

```bash
gh repo fork xdlkc/rock-marketplace --clone=false --remote
```

### 3. 提交 PR

提交信息遵循项目规范 `<type>(<scope>): <description>`（见仓库 CLAUDE.md），scope 用 skill 名：

```bash
git add -A
git commit -m "docs(rock-debug): cap default log search output to avoid flooding"
git push -u origin fix/rock-debug-log-default-limit

gh pr create \
  --repo xdlkc/rock-marketplace \
  --title "docs(rock-debug): cap default log search output" \
  --body-file <(cat <<'EOF'
## 动机
<这个 PR 解决什么反馈>

## 改动
- <改了什么>

## 验证
<怎么确认改对了，如有>
EOF
)
```

把 PR 链接给用户。

### 4. 无 gh 时回退

push 分支后，给用户网页建 PR 的链接：

```
https://github.com/xdlkc/rock-marketplace/compare
```

或展示 diff，让用户自行决定如何提交。

## 标题规范

- Issue：`[<skill-name>] <一句话问题>`，例 `[rock-eval] retry 文档参数写错`
- PR：`<type>(<skill-name>): <description>`，type 用 `fix`/`docs`/`feat`/`refactor`

## 常见陷阱

- **反馈太空泛**：只说"不好用"无法转成有效 issue，务必补全场景与期望/实际。
- **该提 Issue 却提了 PR**：没有明确改法时别擅自改代码，先 Issue 让维护者拍板。
- **改动越界**：PR 只改反馈相关内容，避免夹带无关重构。
- **版本缺失**：bug 类反馈务必带版本号，维护者据此判断是否已修复。
- **直接 push 到 main**：始终走新分支，不在 main 上直接提交。
