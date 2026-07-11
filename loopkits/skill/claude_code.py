"""Claude Code 嵌入目标。

将 LoopKits 生成的 SKILL.md 导出到 Claude Code 的标准目录结构：

::

    <output_path>/.claude/skills/<skill-name>/SKILL.md

其中 ``using-loopkits`` 作为主入口，Claude Code 会话启动时自动加载。

参考 superpowers 的 ``.claude-plugin/`` 与 ``skills/`` 目录结构。
"""

from __future__ import annotations

import os
from typing import Any

from loopkits.patterns.registry import list_patterns
from loopkits.skill.generator import MASTER_SKILL_NAME, SkillGenerator

__all__ = ["ClaudeCodeTarget"]

# Claude Code 的 skills 根目录（相对于 output_path）
_CLAUDE_SKILLS_DIR = os.path.join(".claude", "skills")


class ClaudeCodeTarget:
    """Claude Code 嵌入目标。

    将 SKILL.md 写入 ``<output_path>/.claude/skills/<name>/SKILL.md``，
    使 Claude Code 在会话启动时自动发现并加载。
    """

    def __init__(self, generator: SkillGenerator | None = None) -> None:
        """初始化嵌入目标。

        Args:
            generator: 可选的 :class:`SkillGenerator`；为 None 则内部新建。
        """
        self._generator: SkillGenerator = generator or SkillGenerator()

    # ------------------------------------------------------------------ #
    # 单个导出
    # ------------------------------------------------------------------ #
    def export(
        self,
        skill_content: str,
        name: str,
        output_path: str,
    ) -> str:
        """将单个 SKILL.md 写入 Claude Code 目录结构。

        Args:
            skill_content: SKILL.md 文本内容。
            name: Skill 名称（kebab-case）。
            output_path: 输出根目录。

        Returns:
            写入的 SKILL.md 绝对路径。
        """
        skill_dir = os.path.join(output_path, _CLAUDE_SKILLS_DIR, name)
        os.makedirs(skill_dir, exist_ok=True)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        with open(skill_file, "w", encoding="utf-8") as fh:
            fh.write(skill_content)
        return skill_file

    # ------------------------------------------------------------------ #
    # 批量导出
    # ------------------------------------------------------------------ #
    def export_all(self, output_path: str) -> list[str]:
        """导出所有注册模式 + 主 Skill ``using-loopkits``。

        Args:
            output_path: 输出根目录。

        Returns:
            写入的文件绝对路径列表（主 Skill 排在首位）。
        """
        written: list[str] = []

        # 1. 主 Skill（会话启动自动加载）
        master_md = self._generator.generate_master_skill()
        written.append(self.export(master_md, MASTER_SKILL_NAME, output_path))

        # 2. 所有注册模式
        for meta in list_patterns():
            md = self._generator.from_pattern(meta.name)
            written.append(self.export(md, meta.name, output_path))

        return written

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    def skills_dir(self, output_path: str) -> str:
        """返回给定输出根目录下的 skills 根目录绝对路径。"""
        return os.path.join(output_path, _CLAUDE_SKILLS_DIR)

    def __repr__(self) -> str:
        return f"<ClaudeCodeTarget generator={self._generator!r}>"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ClaudeCodeTarget) and (
            self._generator == other._generator
        )

    def __hash__(self) -> int:  # pragma: no cover - 仅为保持可哈希语义
        return hash(("ClaudeCodeTarget", id(self._generator)))
