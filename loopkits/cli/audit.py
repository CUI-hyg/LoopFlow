"""``loopflow audit`` 子命令 — Loop Ready 评分。

扫描项目目录，检查 Loop Engineering 所需的关键文件与配置是否存在，
给出 0-100 的 Loop Ready 评分。参考 loop-engineering 的 loop-audit 工具。

用法::

    loopflow audit                  # 扫描当前目录
    loopflow audit /path/to/proj    # 扫描指定目录
    loopflow audit --suggest        # 输出改进建议
    loopflow audit --badge          # 输出 Markdown 徽章
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

__all__ = ["audit", "run_audit"]

console: Console = Console()


# 检查项定义：(名称, 分值, 检查函数, 改进建议)
# 检查函数签名：(root: Path) -> bool
def _check_loop_md(root: Path) -> bool:
    return (root / "LOOP.md").is_file()


def _check_state_md(root: Path) -> bool:
    return (root / "STATE.md").is_file()


def _check_budget(root: Path) -> bool:
    return (root / "loop-budget.yaml").is_file() or (root / "loop-budget.md").is_file()


def _check_constraints(root: Path) -> bool:
    return (root / "loop-constraints.md").is_file()


def _check_skills(root: Path) -> bool:
    """检查 .claude/skills/ 目录存在且至少有一个 SKILL.md。"""
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return False
    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
            return True
    return False


def _check_git(root: Path) -> bool:
    return (root / ".git").exists()  # 文件（worktree）或目录均可


def _check_tests(root: Path) -> bool:
    """检查常见测试目录是否存在。"""
    for name in ("tests", "test"):
        d = root / name
        if d.is_dir() and any(d.iterdir()):
            return True
    # 也检查根目录下是否有 test_*.py / *_test.py
    for py in root.glob("test_*.py"):
        return True
    for py in root.glob("*_test.py"):
        return True
    return False


def _check_worktree(root: Path) -> bool:
    """检查 LOOP.md 中是否提到 worktree 策略，或存在 .git/worktrees 目录。"""
    loop_md = root / "LOOP.md"
    if loop_md.is_file():
        try:
            text = loop_md.read_text(encoding="utf-8").lower()
            if "worktree" in text:
                return True
        except OSError:
            pass
    return (root / ".git" / "worktrees").exists()


def _check_pause_all(root: Path) -> bool:
    """检查 loop-pause-all 杀停开关是否被配置引用。"""
    # 检查 loop-constraints.md 是否提及 loop-pause-all
    constraints = root / "loop-constraints.md"
    if constraints.is_file():
        try:
            text = constraints.read_text(encoding="utf-8").lower()
            if "loop-pause-all" in text or "pause-all" in text:
                return True
        except OSError:
            pass
    # 检查 LOOP.md
    loop_md = root / "LOOP.md"
    if loop_md.is_file():
        try:
            text = loop_md.read_text(encoding="utf-8").lower()
            if "loop-pause-all" in text or "pause-all" in text:
                return True
        except OSError:
            pass
    # 检查 STATE.md 是否有 paused 字段
    state_md = root / "STATE.md"
    if state_md.is_file():
        try:
            text = state_md.read_text(encoding="utf-8").lower()
            if "loop-pause-all" in text or "paused" in text:
                return True
        except OSError:
            pass
    return False


# 检查项清单（顺序即展示顺序）
_CHECKS: list[tuple[str, int, object, str]] = [
    (
        "LOOP.md 存在",
        15,
        _check_loop_md,
        "创建 LOOP.md：描述活跃循环、节奏、级别与 worktree 策略。可用 `loopflow init` 生成。",
    ),
    (
        "STATE.md 存在",
        10,
        _check_state_md,
        "创建 STATE.md：记录当前迭代、待办、已完成与暂停标志。可用 `loopflow init` 生成。",
    ),
    (
        "loop-budget.yaml 存在",
        10,
        _check_budget,
        "创建 loop-budget.yaml：配置 daily_cap、threshold 等预算项。可用 `loopflow init` 生成。",
    ),
    (
        "loop-constraints.md 存在",
        15,
        _check_constraints,
        "创建 loop-constraints.md：声明路径保护、行为规则等约束。可用 `loopflow init` 生成。",
    ),
    (
        ".claude/skills/ 有 SKILL.md",
        15,
        _check_skills,
        "运行 `loopflow skill export --pattern <name> --target claude-code --output .claude/skills/` 导出技能。",
    ),
    (
        "Git 仓库已初始化",
        10,
        _check_git,
        "运行 `git init` 初始化版本控制。",
    ),
    (
        "测试目录存在",
        10,
        _check_tests,
        "创建 tests/ 目录并添加测试文件，确保循环变更可验证。",
    ),
    (
        "Worktree 策略已配置",
        5,
        _check_worktree,
        "在 LOOP.md 中声明 worktree 策略（每个修复在隔离 worktree 中进行）。",
    ),
    (
        "loop-pause-all 杀停开关已配置",
        10,
        _check_pause_all,
        "在 loop-constraints.md 或 LOOP.md 中声明 `loop-pause-all` 杀停开关。",
    ),
]


def run_audit(root: Path) -> tuple[int, list[tuple[str, int, bool, str]]]:
    """执行 Loop Ready 评分，返回 (总分, 检查明细)。

    Args:
        root: 项目根目录。

    Returns:
        (score, details) — score 为 0-100 的整数；details 为
        (名称, 分值, 是否通过, 建议) 列表。
    """
    details: list[tuple[str, int, bool, str]] = []
    score = 0
    for name, points, check_fn, suggest in _CHECKS:
        passed = bool(check_fn(root))  # type: ignore[arg-type]
        if passed:
            score += points
        details.append((name, points, passed, suggest))
    return score, details


def _badge_color(score: int) -> str:
    """根据分数返回徽章颜色。"""
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    if score >= 40:
        return "orange"
    return "red"


@click.command()
@click.argument("path", required=False, default=".")
@click.option("--suggest", is_flag=True, help="输出改进建议（缺失项如何补全）")
@click.option("--badge", is_flag=True, help="输出 Markdown 徽章")
def audit(path: str, suggest: bool, badge: bool) -> None:
    """Loop Ready 评分：扫描项目并给出 0-100 分。

    PATH 为目标目录，默认当前目录。
    """
    root = Path(path).resolve()
    if not root.is_dir():
        click.echo(f"路径不存在或不是目录：{root}", err=True)
        raise SystemExit(1)

    score, details = run_audit(root)

    # 主表格
    table = Table(title=f"Loop Ready 评分 — {root}", show_lines=False)
    table.add_column("检查项", style="cyan", no_wrap=True)
    table.add_column("分值", justify="right", style="magenta")
    table.add_column("状态", justify="center")
    for name, points, passed, _ in details:
        status = "[green]✓[/green]" if passed else "[red]✗[/red]"
        table.add_row(name, str(points), status)
    table.add_row("[bold]总分[/bold]", f"[bold]{score}[/bold]/100", "")
    console.print(table)

    # 改进建议
    if suggest:
        missing = [(n, s) for n, _, p, s in details if not p]
        if not missing:
            console.print("\n[green]✓ 所有检查项已通过，无需改进。[/green]")
        else:
            console.print("\n[bold yellow]改进建议：[/bold yellow]")
            for name, suggestion in missing:
                console.print(f"  [red]✗[/red] [cyan]{name}[/cyan]")
                console.print(f"      {suggestion}")

    # 徽章
    if badge:
        color = _badge_color(score)
        badge_md = (
            f"![Loop Ready]"
            f"(https://img.shields.io/badge/Loop_Ready-{score}-{color})"
        )
        console.print(f"\n[bold]Markdown 徽章：[/bold]")
        click.echo(badge_md)
