"""``loopflow cost`` 子命令 — Token 费用估算。

基于模式的 dry_run 结果估算单次运行的 Token 消耗，并按模型单价计算 N 次运行
的总费用。

用法::

    loopflow cost daily-triage                       # 单次估算（默认 1 次）
    loopflow cost daily-triage --runs 10             # 10 次运行总费用
    loopflow cost pr-babysitter --model claude-opus  # 指定模型
"""

from __future__ import annotations

import json
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from loopflow.patterns.registry import get, list_patterns

__all__ = ["cost"]

console: Console = Console()

# 模型单价（美元 / 1M tokens）— 输入 + 输出
# 注：价格为粗略估算，实际以模型供应商最新定价为准
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet": {
        "input": 3.0,   # $3 / 1M input tokens
        "output": 15.0,  # $15 / 1M output tokens
        "label": "Claude 3.5 Sonnet",
    },
    "claude-opus": {
        "input": 15.0,  # $15 / 1M input tokens
        "output": 75.0,  # $75 / 1M output tokens
        "label": "Claude 3 Opus",
    },
    "claude-haiku": {
        "input": 0.25,
        "output": 1.25,
        "label": "Claude 3 Haiku",
    },
    "gpt-4o": {
        "input": 2.5,
        "output": 10.0,
        "label": "GPT-4o",
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.6,
        "label": "GPT-4o mini",
    },
}


def _estimate_tokens(result: dict[str, Any]) -> tuple[int, int]:
    """基于 dry_run 结果粗略估算单次运行的输入/输出 Token 数。

    估算策略：
    - 输入 Token：模式描述 + SKILL.md 内容 + 扫描项数量 × 每项开销
    - 输出 Token：报告内容长度 + 修复建议数量 × 每条开销

    Args:
        result: pattern.dry_run() 返回的结果字典。

    Returns:
        (input_tokens, output_tokens)
    """
    # 基础上下文开销（模式描述 + SKILL + 约束等）
    base_input = 2000

    # 扫描项数量影响输入
    scanned = result.get("scanned", 0)
    if isinstance(scanned, int):
        # 每个扫描项约 200 token（标题、标签、描述等）
        base_input += scanned * 200
    else:
        base_input += 1000  # 未知时给一个默认值

    # 待办/高优先级项也影响输入
    high_priority = result.get("high_priority", [])
    if isinstance(high_priority, list):
        base_input += len(high_priority) * 150

    # 报告内容长度影响输出
    report = result.get("report", "")
    if isinstance(report, str):
        # 粗略：每 4 字符约 1 token
        output_tokens = len(report) // 4
    else:
        output_tokens = 500

    # 修复建议增加输出
    fixes = result.get("fixes", [])
    if isinstance(fixes, list):
        output_tokens += len(fixes) * 300

    # 最低保底
    output_tokens = max(output_tokens, 300)

    return base_input, output_tokens


def _calculate_cost(
    input_tokens: int, output_tokens: int, model: str
) -> float:
    """计算单次运行的美元费用。"""
    pricing = _MODEL_PRICING.get(model, _MODEL_PRICING["claude-sonnet"])
    cost = (
        input_tokens / 1_000_000 * pricing["input"]
        + output_tokens / 1_000_000 * pricing["output"]
    )
    return cost


@click.command()
@click.argument("pattern_name")
@click.option("--runs", type=click.IntRange(min=1), default=1, help="运行次数（默认 1）")
@click.option(
    "--model",
    type=click.Choice(list(_MODEL_PRICING.keys())),
    default="claude-sonnet",
    help="模型（默认 claude-sonnet）",
)
def cost(pattern_name: str, runs: int, model: str) -> None:
    """估算 PATTERN_NAME 模式的 Token 消耗与费用。

    基于模式的 dry_run 结果估算单次运行的 Token 消耗，
    再按模型单价计算 N 次运行的总费用。
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

    # 执行 dry_run 获取结果
    pattern_instance = pattern_cls()
    dry_result = pattern_instance.dry_run()

    # 估算 Token
    input_tokens, output_tokens = _estimate_tokens(dry_result)
    total_tokens = input_tokens + output_tokens

    # 计算费用
    single_cost = _calculate_cost(input_tokens, output_tokens, model)
    total_cost = single_cost * runs

    pricing = _MODEL_PRICING.get(model, _MODEL_PRICING["claude-sonnet"])

    # 输出信息
    console.print(
        f"\n[bold cyan]LoopFlow Cost[/bold cyan] — 模式: "
        f"[magenta]{pattern_name}[/magenta] | "
        f"模型: [magenta]{pricing['label']}[/magenta]\n"
    )

    # Token 估算表格
    token_table = Table(title="单次运行 Token 估算", show_lines=False)
    token_table.add_column("类别", style="cyan")
    token_table.add_column("Token 数", justify="right", style="magenta")
    token_table.add_row("输入 Token", f"{input_tokens:,}")
    token_table.add_row("输出 Token", f"{output_tokens:,}")
    token_table.add_row(
        "[bold]合计[/bold]", f"[bold]{total_tokens:,}[/bold]"
    )
    console.print(token_table)

    # 费用表格
    cost_table = Table(title=f"费用估算（{runs} 次运行）", show_lines=False)
    cost_table.add_column("项目", style="cyan")
    cost_table.add_column("单价（$/1M）", justify="right", style="dim")
    cost_table.add_column("Token 数", justify="right", style="magenta")
    cost_table.add_column("费用（USD）", justify="right", style="green")
    cost_table.add_row(
        "输入",
        f"${pricing['input']:.2f}",
        f"{input_tokens:,}",
        f"${input_tokens / 1_000_000 * pricing['input']:.4f}",
    )
    cost_table.add_row(
        "输出",
        f"${pricing['output']:.2f}",
        f"{output_tokens:,}",
        f"${output_tokens / 1_000_000 * pricing['output']:.4f}",
    )
    cost_table.add_row(
        "[bold]单次合计[/bold]",
        "",
        f"[bold]{total_tokens:,}[/bold]",
        f"[bold green]${single_cost:.4f}[/bold green]",
    )
    if runs > 1:
        cost_table.add_row(
            f"[bold]{runs} 次合计[/bold]",
            "",
            f"[bold]{total_tokens * runs:,}[/bold]",
            f"[bold green]${total_cost:.4f}[/bold green]",
        )
    console.print(cost_table)

    # JSON 输出提示
    json_summary = {
        "pattern": pattern_name,
        "model": model,
        "runs": runs,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "single_run_cost_usd": round(single_cost, 4),
        "total_cost_usd": round(total_cost, 4),
    }
    console.print(
        f"\n[dim]JSON 摘要：[/dim] {json.dumps(json_summary, ensure_ascii=False)}"
    )
