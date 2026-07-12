"""``loopflow run`` 子命令 — 运行循环模式。

从注册表获取模式，构建 Loop 并执行。支持 dry-run 模拟运行。

用法::

    loopflow run daily-triage                  # 运行 daily-triage（默认 L1）
    loopflow run pr-babysitter --level L2      # L2 辅助修复
    loopflow run daily-triage --dry-run        # 模拟运行（不触碰真实服务）
    loopflow run ci-sweeper --max-iterations 5 # 指定最大迭代数
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from loopflow.core.loop import TrustLevel
from loopflow.core.state import State
from loopflow.patterns.registry import get, list_patterns

__all__ = ["run"]

console: Console = Console()


def _format_value(value: Any, depth: int = 0) -> str:
    """递归格式化值为可读字符串。"""
    if depth > 3:
        return "..."
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            lines.append(f"{'  ' * (depth + 1)}{k}: {_format_value(v, depth + 1)}")
        return "\n" + "\n".join(lines)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        lines = []
        for item in value:
            lines.append(f"{'  ' * (depth + 1)}- {_format_value(item, depth + 1)}")
        return "\n" + "\n".join(lines)
    return str(value)


@click.command()
@click.argument("pattern_name")
@click.option(
    "--level",
    type=click.Choice(["L1", "L2", "L3"]),
    default=None,
    help="信任级别覆盖：L1 仅报告 / L2 辅助修复 / L3 全自动",
)
@click.option("--dry-run", is_flag=True, help="模拟运行（不执行实际操作）")
@click.option(
    "--max-iterations",
    type=int,
    default=None,
    help="最大迭代次数（默认由模式决定）",
)
def run(
    pattern_name: str,
    level: str | None,
    dry_run: bool,
    max_iterations: int | None,
) -> None:
    """运行指定的循环模式 PATTERN_NAME。

    从模式注册表获取模式，调用 build_loop() 构建 Loop 并执行。
    --dry-run 时调用 pattern.dry_run() 不实际执行。
    运行后更新当前目录的 STATE.md。
    """
    # 校验模式
    pattern_cls = get(pattern_name)
    if pattern_cls is None:
        available = [m.name for m in list_patterns()]
        click.echo(
            f"模式不存在：{pattern_name}。可用模式：{', '.join(available)}",
            err=True,
        )
        raise SystemExit(1)

    # 确定信任级别
    trust_level: TrustLevel | None = None
    if level is not None:
        trust_level = TrustLevel(level)

    # 实例化模式
    pattern_instance = pattern_cls(level=trust_level)
    effective_level = pattern_instance.effective_level

    console.print(
        f"\n[bold cyan]LoopFlow Run[/bold cyan] — 模式: "
        f"[magenta]{pattern_name}[/magenta] | "
        f"级别: [magenta]{effective_level.value}[/magenta] | "
        f"{'模拟运行' if dry_run else '实际运行'}\n"
    )

    # 检查暂停状态（非 dry-run 时）
    state_path = Path("STATE.md")
    if not dry_run and state_path.exists():
        state = State.load(state_path)
        if state.is_paused():
            console.print(
                "[bold red]⏸ loop-pause-all 已激活，循环未启动。[/bold red]"
            )
            console.print(
                "[dim]使用 `loopflow state resume` 清除暂停标志后重试。[/dim]"
            )
            raise SystemExit(0)

    if dry_run:
        # 模拟运行：调用 pattern.dry_run()
        console.print("[dim]正在执行 dry-run（使用 mock 数据）...[/dim]")
        result = pattern_instance.dry_run()
        _print_dry_run_result(pattern_name, result)
        return

    # 实际运行：构建 Loop
    config_overrides: dict[str, Any] = {}
    if trust_level is not None:
        config_overrides["level"] = trust_level
    if max_iterations is not None:
        config_overrides["max_iterations"] = max_iterations

    # 加载已有状态（如存在）
    state = State.load(state_path) if state_path.exists() else None
    loop = pattern_instance.build_loop(config_overrides)
    if state is not None:
        loop.state = state

    console.print("[dim]正在执行循环...[/dim]")
    loop_result = loop.run()

    # 打印运行结果
    _print_run_result(loop_result, effective_level.value)

    # 更新 STATE.md
    loop.state.save(state_path)
    console.print(f"\n[green]✓ 状态已写入：{state_path}[/green]")


def _print_dry_run_result(pattern_name: str, result: dict[str, Any]) -> None:
    """打印 dry-run 结果。"""
    table = Table(title=f"Dry-Run 结果 — {pattern_name}", show_lines=True)
    table.add_column("字段", style="cyan", no_wrap=True)
    table.add_column("值", style="white")

    for key, value in result.items():
        formatted = _format_value(value)
        table.add_row(key, formatted)

    console.print(table)


def _print_run_result(loop_result: Any, level: str) -> None:
    """打印实际运行结果。"""
    # 摘要面板
    success = loop_result.success
    status_text = "[green]✓ 成功[/green]" if success else "[yellow]● 未达成[/yellow]"
    summary = (
        f"[bold]状态：[/bold] {status_text}\n"
        f"[bold]迭代次数：[/bold] {loop_result.iterations}\n"
        f"[bold]级别：[/bold] {level}\n"
        f"[bold]停止原因：[/bold] {loop_result.stop_reason or '(无)'}"
    )
    console.print(Panel(summary, title="运行结果", border_style="cyan"))

    # 迭代历史表格
    if loop_result.history:
        table = Table(title="迭代历史", show_lines=False)
        table.add_column("迭代", justify="right", style="cyan")
        table.add_column("级别", style="magenta")
        table.add_column("目标达成", justify="center")
        table.add_column("预算占比", justify="right")
        for rec in loop_result.history:
            goal_reached = (
                "[green]✓[/green]"
                if rec.get("goal_reached")
                else "[red]✗[/red]"
            )
            table.add_row(
                str(rec.get("iteration", "?")),
                str(rec.get("level", "?")),
                goal_reached,
                f"{rec.get('budget_ratio', 0) * 100:.1f}%",
            )
        console.print(table)

    # 最终状态
    if loop_result.final_state:
        fs = loop_result.final_state
        fs_lines = []
        for k, v in fs.items():
            fs_lines.append(f"[cyan]{k}[/cyan]: {v}")
        console.print(
            Panel(
                "\n".join(fs_lines),
                title="最终状态快照",
                border_style="dim",
            )
        )
