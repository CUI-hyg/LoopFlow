"""``loopflow skill`` 子命令组。

提供 Skill 导出与嵌入的命令行入口：

- ``loopflow skill generate <pattern>``：生成单个模式的 SKILL.md 并打印。
- ``loopflow skill master``：生成主 Skill ``using-loopkits`` 并打印。
- ``loopflow skill export --pattern <name> --target claude-code --output <path>``：导出单个模式。
- ``loopflow skill export --all --target claude-code --output <path>``：导出全部模式 + 主 Skill。
- ``loopflow skill list``：列出所有可导出的模式。
"""

from __future__ import annotations

import click

from loopkits.patterns.registry import list_patterns
from loopkits.skill import (
    ClaudeCodeTarget,
    CodexTarget,
    SkillGenerator,
)

# 支持的导出目标映射
_TARGETS = {
    "claude-code": ClaudeCodeTarget,
    "codex": CodexTarget,
}


@click.group()
def skill() -> None:
    """生成与导出 SKILL.md（Claude Code / Codex）。"""


@skill.command("list")
def skill_list() -> None:
    """列出所有可导出的循环模式。"""
    patterns = list_patterns()
    if not patterns:
        click.echo("（暂无已注册模式）")
        return
    click.echo(f"已注册模式（共 {len(patterns)} 个）：")
    for meta in patterns:
        cadence = meta.cadence or "—"
        tags = ", ".join(meta.tags) if meta.tags else "—"
        click.echo(
            f"  • {meta.name} — {meta.description}\n"
            f"      节奏: {cadence} | 级别: {meta.default_level.value} | 标签: {tags}"
        )


@skill.command("generate")
@click.argument("pattern_name")
def skill_generate(pattern_name: str) -> None:
    """生成单个模式的 SKILL.md 并输出到 stdout。"""
    gen = SkillGenerator()
    try:
        md = gen.from_pattern(pattern_name)
    except KeyError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1)
    click.echo(md)


@skill.command("master")
def skill_master() -> None:
    """生成主 Skill ``using-loopkits`` 并输出到 stdout。"""
    gen = SkillGenerator()
    click.echo(gen.generate_master_skill())


@skill.command("export")
@click.option(
    "--pattern",
    "pattern_name",
    default=None,
    help="要导出的模式名称（与 --all 二选一；两者都未指定时默认导出全部）",
)
@click.option(
    "--all",
    "export_all",
    is_flag=True,
    help="导出全部模式 + 主 Skill（与 --pattern 二选一）",
)
@click.option(
    "--target",
    "target_name",
    required=True,
    type=click.Choice(list(_TARGETS.keys())),
    help="导出目标（claude-code / codex）",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(file_okay=False),
    help="输出根目录",
)
def skill_export(
    pattern_name: str | None,
    export_all: bool,
    target_name: str,
    output_path: str,
) -> None:
    """导出 SKILL.md 到指定目标目录。

    使用 --pattern <name> 导出单个模式，或 --all 导出全部模式 + 主 Skill。
    两者都未指定时，默认导出全部（等价于 --all）。
    """
    # 校验参数互斥
    if pattern_name and export_all:
        click.echo("--pattern 与 --all 不能同时使用。", err=True)
        raise SystemExit(1)

    target_cls = _TARGETS[target_name]
    target = target_cls()

    if pattern_name:
        # 单个模式导出
        gen = SkillGenerator()
        try:
            md = gen.from_pattern(pattern_name)
        except KeyError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(1)
        files = [target.export(md, pattern_name, output_path)]
        click.echo(
            f"✓ 已导出 1 个模式到 {output_path}（目标：{target_name}）"
        )
    else:
        # 全部导出（含主 Skill）
        files = target.export_all(output_path)
        click.echo(
            f"✓ 已导出 {len(files)} 个文件到 {output_path}（目标：{target_name}）"
        )
    for f in files:
        click.echo(f"  • {f}")
