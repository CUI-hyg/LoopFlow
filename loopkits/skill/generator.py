"""SKILL.md 生成器。

从 LoopKits 的 :class:`Pattern` 生成符合 Claude Code Skill 规范的 ``SKILL.md``
文档，并产出主 Skill ``using-loopkits``（会话启动注入，强制使用相关模式）。

设计要点：

- :class:`SkillConfig` 用 pydantic 描述 Skill 的可结构化字段（名称、描述、触发
  条件、步骤、验证、约束）。
- :class:`SkillGenerator` 通过模式注册表 (:mod:`loopkits.patterns.registry`)
  按名获取模式，调用其 :meth:`Pattern.to_skill_md` 取得人可读片段，并补充头部
  YAML front-matter 与标准章节，最终输出完整 SKILL.md。
- ``generate_master_skill()`` 参考 superpowers 的 using-superpowers，用强制语气
  声明"如有相关 LoopKits 模式适用当前任务，必须使用，不可跳过"。

用法::

    from loopkits.skill import SkillGenerator

    gen = SkillGenerator()
    md = gen.from_pattern("daily-triage")
    master = gen.generate_master_skill()
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from loopkits.patterns.base import Pattern
from loopkits.patterns.registry import get, list_patterns

__all__ = ["SkillConfig", "SkillGenerator"]

# 主 Skill 的固定名称（Claude Code 会话启动自动加载）
MASTER_SKILL_NAME = "using-loopkits"


class SkillConfig(BaseModel):
    """Skill 的结构化配置。

    Attributes:
        name: Skill 唯一标识（kebab-case，如 ``daily-triage``）。
        description: 一句话描述，用于 YAML front-matter 与列表展示。
        trigger: 触发条件描述（When to activate）。
        steps: 执行步骤列表（每个元素是一段步骤说明）。
        verification: 验证规则列表（验证完成与否的判定标准）。
        constraints: 约束列表（不可触碰的红线，如 denylist 路径）。
        body: 可选的完整正文；非空时优先于 steps/verification/constraints 拼接，
            用于直接采用 Pattern 自带的 :meth:`to_skill_md` 内容。
    """

    name: str
    description: str
    trigger: str = ""
    steps: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    body: str = ""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        """pydantic v2 兼容：返回普通字典。"""
        return {
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "steps": list(self.steps),
            "verification": list(self.verification),
            "constraints": list(self.constraints),
            "body": self.body,
        }


class SkillGenerator:
    """从 Pattern 生成完整 SKILL.md。

    生成的文档符合 Claude Code Skill 规范：

    - 顶部 YAML front-matter（``name`` / ``description``）
    - 触发条件（When to activate）
    - 执行步骤（Steps）
    - 验证规则（Verification）
    - 约束（Constraints）
    """

    # ------------------------------------------------------------------ #
    # 公开 API
    # ------------------------------------------------------------------ #
    def from_pattern(self, pattern_name: str) -> str:
        """按名从注册表获取模式，生成完整 SKILL.md。

        Args:
            pattern_name: 模式名称（如 ``daily-triage``）。

        Returns:
            完整的 SKILL.md 字符串。

        Raises:
            KeyError: 模式名未在注册表中找到。
        """
        pattern_cls = get(pattern_name)
        if pattern_cls is None:
            raise KeyError(f"未在注册表中找到模式：{pattern_name}")
        return self.from_pattern_obj(pattern_cls())

    def from_pattern_obj(self, pattern: Pattern) -> str:
        """直接从 Pattern 对象生成完整 SKILL.md。

        优先采用 Pattern 自带的 :meth:`to_skill_md` 作为正文，再补充统一的
        YAML front-matter 与章节标题，使输出既保留模式自定义内容，又符合
        Claude Code Skill 规范。

        Args:
            pattern: :class:`Pattern` 实例。

        Returns:
            完整的 SKILL.md 字符串。
        """
        meta = pattern.meta
        body = pattern.to_skill_md().strip()
        # 去掉 Pattern 自带的 H1 标题（避免与 front-matter 后的标题重复）
        if body.startswith("# "):
            body_lines = body.splitlines()
            body = "\n".join(body_lines[1:]).strip()

        # 触发场景：基于 meta.tags 与 cadence 推断
        trigger = self._infer_trigger(pattern)

        config = SkillConfig(
            name=meta.name,
            description=meta.description,
            trigger=trigger,
            body=body,
        )
        return self.render(config)

    def generate_master_skill(self) -> str:
        """生成主 Skill ``using-loopkits``。

        参考 superpowers 的 using-superpowers，用强制语气声明：会话启动时自动
        加载；如果 LoopKits 模式适用当前任务，必须使用，不可跳过。
        """
        # 列出所有可用模式及其触发场景
        pattern_lines: list[str] = []
        for meta in list_patterns():
            tags = ", ".join(meta.tags) if meta.tags else "—"
            cadence = meta.cadence or "—"
            pattern_lines.append(
                f"- **{meta.name}** — {meta.description}  \n"
                f"  节奏：`{cadence}` | 标签：`{tags}` | 默认级别：`{meta.default_level.value}`"
            )
        patterns_block = "\n".join(pattern_lines)

        description = (
            "Use when starting any conversation involving repository maintenance, "
            "issue/PR triage, CI repair, dependency upgrades, or changelog drafting "
            "- establishes how to discover and run LoopKits patterns, requiring "
            "pattern invocation before acting on relevant tasks"
        )

        body = f"""# Using LoopKits

<EXTREMELY-IMPORTANT>
If you think there is even a 1% chance a LoopKits pattern might apply to what you are doing, you ABSOLUTELY MUST invoke the pattern.

IF A LOOPKITS PATTERN APPLIES TO YOUR TASK, YOU DO NOT HAVE A CHOICE. YOU MUST USE IT.

This is not negotiable. You cannot rationalize your way out of this.
</EXTREMELY-IMPORTANT>

## The Rule

**Invoke relevant LoopKits patterns BEFORE any response or action** — including
clarifying questions, exploring the codebase, or checking files. If it turns out
wrong for the situation, you don't have to run the full loop.

**Before entering implementation:** if a LoopKits pattern applies, audit project
readiness first, then run the loop with the appropriate trust level (L1 report /
L2 assist / L3 autonomous).

Then announce "Using LoopKits pattern `<name>` to <purpose>" and follow the
pattern's steps exactly. If it has a checklist, create a todo per item.

## Available Patterns

{patterns_block}

## Workflow

1. **Audit readiness** — 检查项目是否具备运行循环所需的服务凭证（GitHub /
   Slack / 邮件等）。无凭证时回退到 ``dry_run``，使用 mock 数据。
2. **Pick the pattern** — 按任务类型匹配上表中的模式（如每日分诊 →
   `daily-triage`，新 PR → `pr-babysitter`，CI 失败 → `ci-sweeper`）。
3. **Choose trust level** — L1 仅报告 / L2 辅助修复 / L3 全自动。默认 L1。
4. **Run the loop** — 通过 ``pattern.build_loop().run()`` 或
   ``pattern.dry_run()`` 执行。
5. **Verify** — 检查 :class:`LoopResult` 与模式输出，确认验证规则通过。
6. **Update state** — 将结果写回 STATE.md，便于下一次迭代继承上下文。

## Red Flags

These thoughts mean STOP — you're rationalizing:

| Thought | Reality |
|---------|---------|
| "This is just a quick triage" | Triage IS the task. Use `daily-triage`. |
| "I need more context first" | Pattern check comes BEFORE exploring. |
| "Let me just fix this PR quickly" | Use `pr-babysitter` to review first. |
| "CI is flaky, I'll retry" | Use `ci-sweeper` for root cause. |
| "I'll bump deps manually" | Use `dependency-sweeper` for safety. |
| "This pattern is overkill" | Simple things become complex. Use it. |
| "I remember how this works" | Patterns evolve. Read current SKILL.md. |

## Constraints

- 信任级别不可越权：L1 永不写入代码，L2 必须经 verifier 通过，L3 需显式授权。
- 不触碰 denylist 路径（``.env`` / ``secrets`` / ``auth`` / ``credentials`` 等）。
- 单个循环的修复尝试有上限（多数模式 ≤ 3 次），超出则升级给人。
- ``dry_run`` 模式下不触碰任何真实服务，仅返回 mock 结果。
- 所有完成声明必须有验证证据（参考 verification-before-completion）。

## User Instructions

User instructions (CLAUDE.md, AGENTS.md, GEMINI.md, direct requests) take
precedence over patterns, which in turn override default behavior. Only skip
pattern workflows when your human partner has explicitly told you to.
"""

        config = SkillConfig(
            name=MASTER_SKILL_NAME,
            description=description,
            trigger="会话启动时自动加载；任务涉及 issue/PR/CI/依赖/变更日志时强制触发",
            body=body,
        )
        return self.render(config)

    def render(self, config: SkillConfig) -> str:
        """渲染 SKILL.md 模板。

        Args:
            config: :class:`SkillConfig` 实例。

        Returns:
            完整的 SKILL.md 字符串，包含 YAML front-matter 与正文。
        """
        # YAML front-matter（参考 superpowers 的格式）
        front_matter = (
            "---\n"
            f"name: {config.name}\n"
            f'description: "{_escape_yaml(config.description)}"\n'
            "---\n\n"
        )

        # 正文优先采用 config.body；否则按章节拼接
        if config.body.strip():
            body = config.body.strip()
        else:
            body = self._render_sections(config)

        # 确保正文以 H1 开头（若 config.body 已含 H1，则不重复添加）
        if not body.startswith("# "):
            body = f"# Skill: {config.name}\n\n{body}"

        return front_matter + body + "\n"

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    def _render_sections(self, config: SkillConfig) -> str:
        """按标准章节拼接正文（当未提供 body 时使用）。"""
        sections: list[str] = [f"# Skill: {config.name}", ""]

        if config.description:
            sections.append(f"> {config.description}")
            sections.append("")

        if config.trigger:
            sections.append("## When to activate")
            sections.append(config.trigger)
            sections.append("")

        if config.steps:
            sections.append("## Steps")
            for idx, step in enumerate(config.steps, 1):
                sections.append(f"{idx}. {step}")
            sections.append("")

        if config.verification:
            sections.append("## Verification")
            for v in config.verification:
                sections.append(f"- {v}")
            sections.append("")

        if config.constraints:
            sections.append("## Constraints")
            for c in config.constraints:
                sections.append(f"- {c}")
            sections.append("")

        return "\n".join(sections)

    def _infer_trigger(self, pattern: Pattern) -> str:
        """基于 meta 推断触发场景描述。"""
        meta = pattern.meta
        parts: list[str] = []
        if meta.cadence:
            parts.append(f"节奏：`{meta.cadence}`")
        if meta.tags:
            parts.append("标签：`" + "`, `".join(meta.tags) + "`")
        parts.append(f"默认信任级别：`{meta.default_level.value}`")
        return " | ".join(parts)


def _escape_yaml(value: str) -> str:
    """转义 YAML 字符串中的特殊字符（双引号、反斜杠）。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')
