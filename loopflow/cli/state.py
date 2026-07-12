"""``loopflow state`` 子命令组 — 状态管理。

管理当前项目的循环状态文件 ``STATE.md``：

- ``loopflow state show``：显示当前状态内容
- ``loopflow state pause``：激活 loop-pause-all 杀停开关
- ``loopflow state resume``：清除暂停标志
- ``loopflow state reset``：重置状态（迭代归零，保留历史）

用法::

    loopflow state show
    loopflow state pause
    loopflow state resume
    loopflow state reset
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from loopflow.core.state import State

__all__ = ["state"]

console: Console = Console()

# 默认 STATE.md 路径
_DEFAULT_STATE_PATH = "STATE.md"


def _load_state(state_path: Path) -> State:
    """加载状态文件；不存在则返回空 State 并提示。"""
    if not state_path.exists():
        console.print(
            f"[yellow]⚠ 状态文件不存在：{state_path}[/yellow]"
        )
        console.print(
            "[dim]提示：运行 `loopflow init` 生成初始 STATE.md。[/dim]"
        )
        raise SystemExit(1)
    return State.load(state_path)


@click.group()
def state() -> None:
    """管理循环状态文件 STATE.md（show / pause / resume / reset）。"""


@state.command("show")
@click.option(
    "--path",
    "state_path_str",
    default=_DEFAULT_STATE_PATH,
    help="STATE.md 路径（默认 ./STATE.md）",
)
def state_show(state_path_str: str) -> None:
    """显示当前 STATE.md 的内容。"""
    state_path = Path(state_path_str)
    st = _load_state(state_path)

    # 状态摘要面板
    paused_badge = (
        "[red]⏸ PAUSED[/red]" if st.is_paused() else "[green]● ACTIVE[/green]"
    )
    summary = (
        f"[bold]状态：[/bold] {paused_badge}\n"
        f"[bold]当前迭代：[/bold] {st.iteration}\n"
        f"[bold]目标：[/bold] {st.goal or '(未设置)'}\n"
        f"[bold]上次运行：[/bold] {st.last_run or '(未运行)'}\n"
        f"[bold]待办数：[/bold] {len(st.todos)}\n"
        f"[bold]已完成数：[/bold] {len(st.completed)}"
    )
    console.print(Panel(summary, title=f"循环状态 — {state_path}", border_style="cyan"))

    # 待办与已完成表格
    table = Table(title="待办与已完成", show_lines=False)
    table.add_column("状态", justify="center")
    table.add_column("事项", style="white")

    for item in st.todos:
        table.add_row("[yellow]☐[/yellow]", item)
    for item in st.completed:
        table.add_row("[green]✓[/green]", item)
    if not st.todos and not st.completed:
        table.add_row("[dim]—[/dim]", "[dim](暂无事项)[/dim]")
    console.print(table)

    # 备注
    if st.notes:
        console.print(
            Panel(st.notes, title="Notes", border_style="dim")
        )

    # 最近历史
    if st.history:
        hist_table = Table(title="最近迭代历史（最多 10 条）", show_lines=False)
        hist_table.add_column("迭代", justify="right", style="cyan")
        hist_table.add_column("变更摘要", style="white")
        for rec in st.history[-10:]:
            iteration = rec.get("iteration", "?")
            # 截取关键字段构造摘要
            summary_keys = {k: v for k, v in rec.items() if k != "iteration"}
            summary_text = ", ".join(
                f"{k}={v}" for k, v in summary_keys.items()
            )
            if len(summary_text) > 80:
                summary_text = summary_text[:77] + "..."
            hist_table.add_row(str(iteration), summary_text or "(无变更)")
        console.print(hist_table)


@state.command("pause")
@click.option(
    "--path",
    "state_path_str",
    default=_DEFAULT_STATE_PATH,
    help="STATE.md 路径（默认 ./STATE.md）",
)
@click.option(
    "--reason",
    default="loop-pause-all",
    help="暂停原因（默认 loop-pause-all）",
)
def state_pause(state_path_str: str, reason: str) -> None:
    """激活 loop-pause-all 杀停开关。

    所有循环在下次迭代检查时将立即退出。
    """
    state_path = Path(state_path_str)
    st = _load_state(state_path)

    if st.is_paused():
        console.print(
            f"[yellow]⚠ 循环已处于暂停状态。[/yellow]"
        )
        console.print(f"[dim]原因：{st.notes}[/dim]")
        return

    st.mark_paused(reason)
    st.save(state_path)
    console.print(
        f"[bold red]⏸ 已激活 loop-pause-all 杀停开关。[/bold red]"
    )
    console.print(f"[dim]原因：{reason}[/dim]")
    console.print(f"[green]✓ 状态已写入：{state_path}[/green]")
    console.print(
        "[dim]所有循环将在下次迭代检查时立即退出。"
        "使用 `loopflow state resume` 恢复。[/dim]"
    )


@state.command("resume")
@click.option(
    "--path",
    "state_path_str",
    default=_DEFAULT_STATE_PATH,
    help="STATE.md 路径（默认 ./STATE.md）",
)
def state_resume(state_path_str: str) -> None:
    """清除 loop-pause-all 暂停标志，恢复循环。"""
    state_path = Path(state_path_str)
    st = _load_state(state_path)

    if not st.is_paused():
        console.print(
            "[green]● 循环当前处于活动状态，无需恢复。[/green]"
        )
        return

    st.clear_paused()
    st.save(state_path)
    console.print(
        f"[bold green]✓ 已清除 loop-pause-all 暂停标志。[/bold green]"
    )
    console.print(f"[green]✓ 状态已写入：{state_path}[/green]")
    console.print(
        "[dim]循环现在可以正常启动。[/dim]"
    )


@state.command("reset")
@click.option(
    "--path",
    "state_path_str",
    default=_DEFAULT_STATE_PATH,
    help="STATE.md 路径（默认 ./STATE.md）",
)
@click.option(
    "--yes",
    is_flag=True,
    help="跳过确认提示",
)
def state_reset(state_path_str: str, yes: bool) -> None:
    """重置状态：迭代归零、清空待办与已完成，但保留历史记录。"""
    state_path = Path(state_path_str)
    st = _load_state(state_path)

    if not yes:
        click.confirm(
            f"确认重置状态？迭代将从 {st.iteration} 归零，"
            "待办与已完成将被清空（历史保留）。",
            abort=True,
        )

    # 保留历史，重置其他字段
    old_history = list(st.history)
    old_goal = st.goal
    st.iteration = 0
    st.todos = []
    st.completed = []
    st.paused = False
    st.notes = ""
    st.goal = old_goal
    st.history = old_history  # 保留历史
    st.update(iteration=0, action="reset")
    st.save(state_path)

    console.print(
        f"[bold green]✓ 状态已重置。[/bold green]"
    )
    console.print(
        f"[dim]迭代归零，待办与已完成已清空，历史记录保留（{len(old_history)} 条）。[/dim]"
    )
    console.print(f"[green]✓ 状态已写入：{state_path}[/green]")
