"""``loopflow`` CLI 入口。

LoopKits 命令行工具，提供完整的 Loop Engineering 子命令链：

- ``loopflow init``：脚手架初始化（生成 LOOP.md / STATE.md / loop-budget.yaml 等）
- ``loopflow run <pattern>``：运行循环模式
- ``loopflow audit``：Loop Ready 评分
- ``loopflow cost <pattern>``：Token 费用估算
- ``loopflow state``：状态管理（show / pause / resume / reset）
- ``loopflow worktree``：git worktree 管理（create / list / remove / clean）
- ``loopflow skill``：技能文档生成与导出（list / generate / master / export）
- ``loopflow service``：服务连接器管理

同时提供 ``loopflow --version`` 与 ``loopflow --help``。
"""

import click

from loopkits import __version__
from loopkits.cli.audit import audit
from loopkits.cli.cost import cost
from loopkits.cli.init import init
from loopkits.cli.run import run
from loopkits.cli.service import service
from loopkits.cli.skill import skill
from loopkits.cli.state import state
from loopkits.cli.worktree import worktree


@click.group()
@click.version_option(version=__version__, prog_name="loopflow")
def cli() -> None:
    """LoopKits 命令行工具 — LoopFlow = Loops × WorkFlows + Agents & Services."""


@cli.command()
def hello() -> None:
    """占位命令，验证 CLI 入口可用。"""
    click.echo(f"LoopKits v{__version__} — LoopFlow 框架已就绪。")


# 注册所有子命令
cli.add_command(init)
cli.add_command(run)
cli.add_command(audit)
cli.add_command(cost)
cli.add_command(state)
cli.add_command(worktree)
cli.add_command(skill)
cli.add_command(service)


if __name__ == "__main__":
    cli()
