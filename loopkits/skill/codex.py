"""Codex 嵌入目标。

将 LoopKits 生成的 SKILL.md 导出到 Codex 的 plugin 目录结构：

::

    <output_path>/<skill-name>/SKILL.md
    <output_path>/manifest.json

``manifest.json`` 参考 superpowers 的 ``.codex-plugin/plugin.json``，描述插件
元数据与 skills 列表，使 Codex 能发现并加载所有 LoopKits Skill。
"""

from __future__ import annotations

import json
import os
from typing import Any

from loopkits import __version__ as _loopkits_version
from loopkits.patterns.registry import list_patterns
from loopkits.skill.generator import MASTER_SKILL_NAME, SkillGenerator

__all__ = ["CodexTarget"]

# Codex plugin manifest 文件名
_MANIFEST_FILENAME = "manifest.json"


class CodexTarget:
    """Codex 嵌入目标。

    将 SKILL.md 写入 ``<output_path>/<name>/SKILL.md``，并在 ``<output_path>``
    根目录生成 ``manifest.json``，描述插件元数据与所有 skills。
    """

    def __init__(
        self,
        generator: SkillGenerator | None = None,
        *,
        plugin_name: str = "loopkits",
        plugin_version: str = _loopkits_version,
        plugin_description: str = (
            "LoopKits — Loop Engineering patterns (daily triage, PR babysitter, "
            "CI sweeper, dependency sweeper, changelog drafter, etc.) as Codex skills."
        ),
    ) -> None:
        """初始化嵌入目标。

        Args:
            generator: 可选的 :class:`SkillGenerator`；为 None 则内部新建。
            plugin_name: Codex plugin 名称，默认 ``loopkits``。
            plugin_version: plugin 版本，默认取 LoopKits 版本。
            plugin_description: plugin 描述。
        """
        self._generator: SkillGenerator = generator or SkillGenerator()
        self._plugin_name: str = plugin_name
        self._plugin_version: str = plugin_version
        self._plugin_description: str = plugin_description

    # ------------------------------------------------------------------ #
    # 单个导出
    # ------------------------------------------------------------------ #
    def export(
        self,
        skill_content: str,
        name: str,
        output_path: str,
    ) -> str:
        """将单个 SKILL.md 写入 Codex 目录结构。

        注意：单次 ``export`` 不会更新 ``manifest.json``；如需完整的 manifest，
        请使用 :meth:`export_all`。

        Args:
            skill_content: SKILL.md 文本内容。
            name: Skill 名称（kebab-case）。
            output_path: 输出根目录。

        Returns:
            写入的 SKILL.md 绝对路径。
        """
        skill_dir = os.path.join(output_path, name)
        os.makedirs(skill_dir, exist_ok=True)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        with open(skill_file, "w", encoding="utf-8") as fh:
            fh.write(skill_content)
        return skill_file

    # ------------------------------------------------------------------ #
    # 批量导出
    # ------------------------------------------------------------------ #
    def export_all(self, output_path: str) -> list[str]:
        """导出所有注册模式 + 主 Skill，并生成 ``manifest.json``。

        Args:
            output_path: 输出根目录。

        Returns:
            写入的文件绝对路径列表（包含 SKILL.md 与 manifest.json）。
        """
        written: list[str] = []
        skills_meta: list[dict[str, str]] = []

        # 1. 主 Skill（会话启动注入）
        master_md = self._generator.generate_master_skill()
        master_path = self.export(master_md, MASTER_SKILL_NAME, output_path)
        written.append(master_path)
        skills_meta.append(
            {
                "name": MASTER_SKILL_NAME,
                "path": f"{MASTER_SKILL_NAME}/SKILL.md",
                "description": (
                    "Master skill: auto-loaded at session start; mandates use of "
                    "applicable LoopKits patterns."
                ),
            }
        )

        # 2. 所有注册模式
        for meta in list_patterns():
            md = self._generator.from_pattern(meta.name)
            skill_path = self.export(md, meta.name, output_path)
            written.append(skill_path)
            skills_meta.append(
                {
                    "name": meta.name,
                    "path": f"{meta.name}/SKILL.md",
                    "description": meta.description,
                }
            )

        # 3. 生成 manifest.json（参考 superpowers/.codex-plugin/plugin.json）
        manifest = self._build_manifest(skills_meta)
        manifest_path = os.path.join(output_path, _MANIFEST_FILENAME)
        os.makedirs(output_path, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        written.append(manifest_path)

        return written

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    def _build_manifest(
        self,
        skills_meta: list[dict[str, str]],
    ) -> dict[str, Any]:
        """构建 Codex plugin manifest 字典。

        参考 superpowers 的 ``.codex-plugin/plugin.json`` 结构。
        """
        return {
            "name": self._plugin_name,
            "version": self._plugin_version,
            "description": self._plugin_description,
            "skills": skills_meta,
            # 标准字段（参考 superpowers）
            "homepage": "https://github.com/loopkits/loopkits",
            "license": "MIT",
            "keywords": [
                "loop-engineering",
                "triage",
                "ci",
                "automation",
                "skills",
                "workflows",
            ],
        }

    def manifest_path(self, output_path: str) -> str:
        """返回给定输出根目录下的 manifest.json 绝对路径。"""
        return os.path.join(output_path, _MANIFEST_FILENAME)

    def __repr__(self) -> str:
        return (
            f"<CodexTarget plugin={self._plugin_name!r} "
            f"version={self._plugin_version!r}>"
        )

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, CodexTarget) and (
            self._plugin_name == other._plugin_name
            and self._plugin_version == other._plugin_version
        )

    def __hash__(self) -> int:  # pragma: no cover - 仅为保持可哈希语义
        return hash(("CodexTarget", self._plugin_name, self._plugin_version))
