"""Skill 导出与嵌入。

将 LoopKits 的循环模式 (:mod:`loopkits.patterns`) 生成为符合 Claude Code /
Codex Skill 规范的 ``SKILL.md``，并嵌入到对应的目标目录结构。

核心组件：

- :class:`SkillConfig` — Skill 的结构化配置（名称、描述、触发、步骤、验证、约束）。
- :class:`SkillGenerator` — 从 Pattern 生成 SKILL.md，含主 Skill
  ``using-loopkits``（会话启动注入，强制使用相关模式）。
- :class:`ClaudeCodeTarget` — 嵌入到 Claude Code 的 ``.claude/skills/`` 目录。
- :class:`CodexTarget` — 嵌入到 Codex 的 plugin 目录结构 + ``manifest.json``。

用法::

    from loopkits.skill import SkillGenerator, ClaudeCodeTarget, CodexTarget

    gen = SkillGenerator()
    md = gen.from_pattern("daily-triage")          # 单个模式
    master = gen.generate_master_skill()           # 主 Skill

    # 导出到 Claude Code
    ClaudeCodeTarget().export_all("/path/to/project")

    # 导出到 Codex
    CodexTarget().export_all("/path/to/project")
"""

from loopkits.skill.claude_code import ClaudeCodeTarget
from loopkits.skill.codex import CodexTarget
from loopkits.skill.generator import (
    MASTER_SKILL_NAME,
    SkillConfig,
    SkillGenerator,
)

__all__ = [
    "SkillConfig",
    "SkillGenerator",
    "ClaudeCodeTarget",
    "CodexTarget",
    "MASTER_SKILL_NAME",
]
