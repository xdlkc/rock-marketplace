# Rock Agents 插件规范

## 插件目录结构

```
plugins/<plugin-name>/
├── plugin.json          # 必须：插件元数据
├── hooks/
│   └── hooks.json       # 可选：Claude Code hooks 配置
└── skills/
    └── <skill-name>/
        ├── SKILL.md     # 必须：技能主文件
        └── ...          # 可选：附属资源（脚本、参考文档等）
```

## plugin.json 格式

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "插件描述",
  "author": "作者",
  "skills": ["skill-name-1", "skill-name-2"]
}
```

## SKILL.md 格式

```markdown
---
name: skill-name
description: 技能描述，用于触发判断。越详细越好，包含触发场景和关键词。
---

# 技能标题

技能内容...
```

## hooks.json 格式

遵循 Claude Code hooks 规范：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "关键词匹配",
        "hooks": [
          {
            "type": "command",
            "command": "命令",
            "async": false
          }
        ]
      }
    ]
  }
}
```

## 命名规范

- 插件名：`kebab-case`，全小写
- 技能名：`kebab-case`，全小写
- 版本：遵循 semver（`major.minor.patch`）
