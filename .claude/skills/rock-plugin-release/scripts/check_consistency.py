#!/usr/bin/env python3
"""
rock-plugin-release 一致性校验脚本

检查 plugin 仓库中六处关键位置之间的一致性：
  1. plugins/<plugin>/plugin.json        — 插件元数据（version/description）
  2. marketplace/registry.json           — marketplace 注册表（version/description/skills 列表/updated_at）
  3. plugins/<plugin>/skills/<skill>/    — 实际 skill 目录
  4. skills/<skill>                       — 顶层软链（兼容 npx skills add）
  5. .claude-plugin/marketplace.json     — Claude Code plugin marketplace 清单（description）
  6. README.md                            — 结构图与技能表格

退出码：0 = 全部一致；1 = 发现不一致或错误。
设计为可重复运行、人类可读，不修改任何文件。
"""
import json
import os
import re
import sys
from pathlib import Path


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{path} 不存在"
    except json.JSONDecodeError as e:
        return None, f"{path} JSON 解析失败：{e}"


def main():
    # scripts/ -> skill -> .claude/skills/x -> .claude/skills -> .claude -> repo(root)
    repo = Path(__file__).resolve().parents[4]
    if not (repo / "plugins").exists():
        repo = Path(os.environ.get("ROCK_MARKETPLACE_ROOT", os.getcwd())).resolve()

    errors = []   # 硬错误：必须修复
    warnings = [] # 软警告：建议检查

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    # ---- 定位 plugin 目录（约定：单 plugin 仓库，plugins/<name>）----
    plugins_dir = repo / "plugins"
    if not plugins_dir.is_dir():
        err(f"找不到 plugins 目录：{plugins_dir}")
        return _report(repo, errors, warnings)

    plugin_dirs = [d for d in plugins_dir.iterdir() if d.is_dir() and (d / "plugin.json").exists()]
    if not plugin_dirs:
        err("plugins/ 下没有任何包含 plugin.json 的插件目录")
        return _report(repo, errors, warnings)
    if len(plugin_dirs) > 1:
        warn(f"发现多个插件目录，本脚本按单插件约定只检查第一个：{plugin_dirs[0].name}（其余：{[d.name for d in plugin_dirs[1:]]}）")

    plugin = plugin_dirs[0]
    plugin_json, e = _read_json(plugin / "plugin.json")
    if e:
        err(e)
        return _report(repo, errors, warnings)

    registry_path = repo / "marketplace" / "registry.json"
    registry, e = _read_json(registry_path)
    if e:
        err(e)
        return _report(repo, errors, warnings)

    assert plugin_json is not None and registry is not None  # 上面已对解析错误 return

    plugin_name = plugin_json.get("name", plugin.name)

    # ---- registry.json 必须包含该 plugin 条目 ----
    reg_plugins = registry.get("plugins", [])
    reg_entry = next((p for p in reg_plugins if p.get("name") == plugin_name), None)
    if reg_entry is None:
        err(f"registry.json 中找不到插件 '{plugin_name}' 的条目")
        return _report(repo, errors, warnings)

    # ---- 1. version 一致性 ----
    v_plugin = plugin_json.get("version")
    v_reg = reg_entry.get("version")
    if v_plugin != v_reg:
        err(f"版本号不一致：plugin.json = {v_plugin!r}，registry.json = {v_reg!r}（当前仓库就处于这种状态，需统一）")

    if v_plugin:
        if not re.fullmatch(r"\d+\.\d+\.\d+", v_plugin):
            err(f"version 不符合 semver(major.minor.patch)：{v_plugin!r}")
        elif v_plugin == "0.0.0":
            warn(f"version 仍是初始值 0.0.0：{v_plugin!r}（发布前需 bump）")

    # ---- 2. description 一致性 ----
    d_plugin = (plugin_json.get("description") or "").strip()
    d_reg = (reg_entry.get("description") or "").strip()
    if d_plugin and d_reg and d_plugin != d_reg:
        warn(f"description 不一致（建议同步）：\n    plugin.json: {d_plugin}\n    registry.json: {d_reg}")

    # ---- 2b. .claude-plugin/marketplace.json（Claude Code plugin marketplace 清单）----
    # 这是 /plugin marketplace add 读取的清单，含外层 marketplace 与内层各 plugin 的 description。
    # 它是独立于 registry.json 的第六处同步点，极易被遗漏——曾经因新增 skill 时只改 registry 而漏改它，
    # 导致 marketplace 展示的描述与实际 plugin 不符。
    mp_path = repo / ".claude-plugin" / "marketplace.json"
    mp, mp_err_msg = _read_json(mp_path)
    if mp_err_msg:
        warn(f"未读取 .claude-plugin/marketplace.json：{mp_err_msg}（若本仓库不经 /plugin marketplace add 分发可忽略）")
    else:
        assert mp is not None  # mp_err_msg 为空即解析成功
        mp_plugins = mp.get("plugins", [])
        mp_entry = next((p for p in mp_plugins if p.get("name") == plugin_name), None)
        if mp_entry is None:
            warn(f".claude-plugin/marketplace.json 的 plugins[] 中缺少 '{plugin_name}' 条目")
        else:
            d_mp_inner = (mp_entry.get("description") or "").strip()
            # 内层 plugin description 应与 plugin.json/registry.json 大体一致（允许措辞不同，但关键词应跟上）
            for kw in ("CLI", "沙箱", "Agent", "评测"):
                if kw in d_reg and kw not in d_mp_inner:
                    warn(f".claude-plugin/marketplace.json 内层 plugin description 似乎缺少关键词 {kw!r}（registry 已有）：\n    marketplace.json: {d_mp_inner}")
                    break
            mp_src = (mp_entry.get("source") or "").strip()
            if mp_src and mp_src != f"./plugins/{plugin_name}":
                warn(f".claude-plugin/marketplace.json 的 source 应为 './plugins/{plugin_name}'，实为 {mp_src!r}")

    # ---- 3. registry path 指向正确 ----
    reg_path = reg_entry.get("path")
    expected_path = f"plugins/{plugin_name}"
    if reg_path != expected_path:
        err(f"registry.json path 应为 {expected_path!r}，实为 {reg_path!r}")

    # ---- 4. skills 列表 vs 实际目录 ----
    skills_dir = plugin / "skills"
    actual_skill_dirs = sorted(
        d.name for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    ) if skills_dir.is_dir() else []
    if not skills_dir.is_dir():
        err(f"找不到插件 skills 目录：{skills_dir}")

    reg_skills = reg_entry.get("skills", [])
    missing_in_reg = sorted(set(actual_skill_dirs) - set(reg_skills))
    missing_on_disk = sorted(set(reg_skills) - set(actual_skill_dirs))
    if missing_in_reg:
        err(f"registry.json skills 列表缺少实际存在的目录：{missing_in_reg}")
    if missing_on_disk:
        err(f"registry.json skills 列表中有目录已不存在的条目：{missing_on_disk}")

    # 顺序一致性（仅当集合一致时提示）
    if not missing_in_reg and not missing_on_disk and reg_skills != actual_skill_dirs:
        warn(f"registry.json skills 顺序与目录不一致（建议按目录字母序）：registry={reg_skills} disk={actual_skill_dirs}")

    # ---- 5. 每个 skill 必须有合法 SKILL.md frontmatter ----
    for sname in actual_skill_dirs:
        skill_md = skills_dir / sname / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            err(f"{sname}/SKILL.md 缺少 YAML frontmatter（应以 --- 开头）")
            continue
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            err(f"{sname}/SKILL.md frontmatter 格式不合法")
            continue
        fm = m.group(1)
        if not re.search(r"^name:\s*" + re.escape(sname) + r"\s*$", fm, re.MULTILINE):
            warn(f"{sname}/SKILL.md 的 name 字段与目录名不一致或缺失")
        if "description" not in fm:
            warn(f"{sname}/SKILL.md 缺少 description 字段（影响触发）")

    # ---- 6. 顶层 skills/<skill> 软链 ----
    top_skills = repo / "skills"
    for sname in actual_skill_dirs:
        link = top_skills / sname
        if not link.exists():
            warn(f"顶层软链缺失或失效：skills/{sname}（兼容 npx skills add 需要它）")
            continue
        if not link.is_symlink():
            warn(f"skills/{sname} 不是软链（应为指向 ../plugins/{plugin_name}/skills/{sname} 的软链）")
            continue
        target = link.resolve()
        expected_target = (skills_dir / sname).resolve()
        if target != expected_target:
            warn(f"skills/{sname} 软链指向错误：{target}（期望 {expected_target}）")

    # 检查多余的顶层软链
    if top_skills.is_dir():
        for item in top_skills.iterdir():
            if item.is_symlink() and item.name not in actual_skill_dirs:
                warn(f"顶层存在多余/失效的软链：skills/{item.name}（对应 skill 已不存在）")

    # ---- 7. updated_at 合理性 ----
    updated_at = registry.get("updated_at")
    if updated_at:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated_at):
            warn(f"registry.json updated_at 格式应为 YYYY-MM-DD：{updated_at!r}")
        # 未来日期检查需要日期库，用字符串比较兜底
        today = os.environ.get("ROCK_TODAY")
        if today and updated_at > today:
            warn(f"registry.json updated_at 是未来日期：{updated_at!r}（今天 {today}）")

    # ---- 8. README.md 中是否提到所有 skill ----
    readme = repo / "README.md"
    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        for sname in actual_skill_dirs:
            if sname not in readme_text:
                warn(f"README.md 中未提到 skill '{sname}'（结构图或技能表格可能漏更新）")

    return _report(repo, errors, warnings)


def _report(repo, errors, warnings):
    print(f"仓库：{repo}")
    print("=" * 60)
    if not errors and not warnings:
        print("✅ 一致性检查通过，六处位置同步正常。")
        return 0

    if errors:
        print(f"❌ 发现 {len(errors)} 个必须修复的问题：")
        for i, m in enumerate(errors, 1):
            print(f"  {i}. {m}")
    if warnings:
        print(f"\n⚠️  发现 {len(warnings)} 个建议检查的告警：")
        for i, m in enumerate(warnings, 1):
            print(f"  {i}. {m}")

    print("\n提示：新增/删除/更新 skill 后，务必同步这六处：")
    print("  1) plugins/rock/skills/<skill>/      实际内容")
    print("  2) skills/<skill>                    顶层软链（新增时创建）")
    print("  3) plugins/rock/plugin.json          version + description")
    print("  4) marketplace/registry.json         version + description + skills 列表 + updated_at")
    print("  5) .claude-plugin/marketplace.json   marketplace 清单的 description（极易漏！）")
    print("  6) README.md                         结构图 + 技能表格")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
