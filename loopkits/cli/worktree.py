"""``loopflow worktree`` 子命令组 — git worktree 管理。

为循环运行创建隔离的 git worktree，避免污染主工作区。使用 gitpython 库。

用法::

    loopflow worktree create --run-id 001 --pattern daily-triage
    loopflow worktree list
    loopflow worktree remove <path>
    loopflow worktree clean
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

__all__ = ["worktree"]

console: Console = Console()


def _get_repo():
    """获取当前 git 仓库对象；非 git 仓库则提示并退出。"""
    try:
        from git import InvalidGitRepositoryError, Repo
    except ImportError:
        click.echo(
            "未安装 gitpython。请运行 `pip install gitpython` 后重试。",
            err=True,
        )
        raise SystemExit(1)

    try:
        repo = Repo(".", search_parent_directories=True)
    except InvalidGitRepositoryError:
        click.echo(
            "当前目录不是 git 仓库。请先运行 `git init` 或切换到 git 仓库根目录。",
            err=True,
        )
        raise SystemExit(1)
    return repo


@click.group()
def worktree() -> None:
    """管理 git worktree（create / list / remove / clean）。"""


@worktree.command("create")
@click.option("--run-id", required=True, help="运行 ID（用于命名 worktree 分支）")
@click.option("--pattern", required=True, help="循环模式名称")
@click.option(
    "--base-branch",
    default=None,
    help="基于的分支（默认当前 HEAD）",
)
def worktree_create(run_id: str, pattern: str, base_branch: str | None) -> None:
    """为一次循环运行创建隔离的 git worktree。

    分支命名：``loop/<pattern>/<run-id>``
    worktree 路径：``../<repo-name>-worktrees/<pattern>-<run-id>``
    """
    repo = _get_repo()

    branch_name = f"loop/{pattern}/{run_id}"
    repo_root = Path(repo.working_tree_dir).resolve()
    repo_name = repo_root.name
    # worktree 放在仓库同级的目录下，避免污染主工作区
    worktree_root = repo_root.parent / f"{repo_name}-worktrees"
    worktree_path = worktree_root / f"{pattern}-{run_id}"

    # 检查分支是否已存在
    existing_branches = [b.name for b in repo.branches]
    if branch_name in existing_branches:
        click.echo(
            f"分支已存在：{branch_name}。请使用不同的 run-id 或先删除该分支。",
            err=True,
        )
        raise SystemExit(1)

    # 检查 worktree 路径是否已存在
    if worktree_path.exists():
        click.echo(
            f"worktree 路径已存在：{worktree_path}",
            err=True,
        )
        raise SystemExit(1)

    # 确定 base commit
    if base_branch:
        try:
            base_commit = repo.commit(base_branch)
        except Exception:
            click.echo(f"找不到 base 分支/commit：{base_branch}", err=True)
            raise SystemExit(1)
    else:
        base_commit = repo.head.commit

    # 创建 worktree + 新分支
    worktree_root.mkdir(parents=True, exist_ok=True)
    try:
        repo.git.worktree("add", "-b", branch_name, str(worktree_path), base_commit.hexsha)
    except Exception as exc:
        click.echo(f"创建 worktree 失败：{exc}", err=True)
        raise SystemExit(1)

    console.print(
        f"[bold green]✓ 已创建 worktree[/bold green]"
    )
    table = Table(show_lines=False)
    table.add_column("项目", style="cyan")
    table.add_column("值", style="white")
    table.add_row("模式", pattern)
    table.add_row("运行 ID", run_id)
    table.add_row("分支", branch_name)
    table.add_row("路径", str(worktree_path))
    table.add_row("基于", base_branch or "HEAD")
    console.print(table)
    console.print(
        f"\n[dim]提示：进入 worktree 后运行 `loopflow run {pattern}` "
        "进行隔离实验。完成后用 `loopflow worktree remove` 清理。[/dim]"
    )


@worktree.command("list")
def worktree_list() -> None:
    """列出所有 git worktree。"""
    repo = _get_repo()

    worktrees = repo.git.worktree("list", "--porcelain").split("\n\n")
    table = Table(title="Git Worktrees", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("路径", style="white")
    table.add_column("分支/Commit", style="magenta")

    idx = 0
    for block in worktrees:
        block = block.strip()
        if not block:
            continue
        path_str = ""
        branch_str = ""
        for line in block.splitlines():
            if line.startswith("worktree "):
                path_str = line[len("worktree "):]
            elif line.startswith("branch "):
                branch_str = line[len("branch "):]
            elif line.startswith("detached"):
                branch_str = "(detached)"
            elif line.startswith("HEAD "):
                if not branch_str:
                    branch_str = line[len("HEAD "):][:8]
        idx += 1
        # 标记主仓库
        is_main = Path(path_str).resolve() == Path(repo.working_tree_dir).resolve()
        marker = " [green](main)[/green]" if is_main else ""
        table.add_row(str(idx), path_str + marker, branch_str)

    if idx == 0:
        console.print("[yellow]（暂无 worktree）[/yellow]")
    else:
        console.print(table)


@worktree.command("remove")
@click.argument("path")
@click.option("--force", is_flag=True, help="强制删除（即使有未提交改动）")
def worktree_remove(path: str, force: bool) -> None:
    """删除指定路径的 worktree。

    PATH 为 worktree 的路径。
    """
    repo = _get_repo()

    wt_path = Path(path).resolve()
    if not wt_path.exists():
        click.echo(f"worktree 路径不存在：{wt_path}", err=True)
        raise SystemExit(1)

    # 防止误删主仓库
    main_path = Path(repo.working_tree_dir).resolve()
    if wt_path == main_path:
        click.echo("不能删除主仓库工作区。", err=True)
        raise SystemExit(1)

    args = ["worktree", "remove", str(wt_path)]
    if force:
        args.append("--force")
    try:
        repo.git.execute(["git"] + args)
    except Exception as exc:
        click.echo(f"删除 worktree 失败：{exc}", err=True)
        raise SystemExit(1)

    console.print(f"[green]✓ 已删除 worktree：{wt_path}[/green]")

    # 尝试删除关联的 loop/ 分支（如果已无 worktree 引用）
    # 查找是否有同名分支可清理
    branch_name = ""
    try:
        for line in repo.git.worktree("list", "--porcelain").splitlines():
            if line.startswith("branch "):
                pass  # 仅用于检测
    except Exception:
        pass
    if branch_name:
        console.print(f"[dim]关联分支 {branch_name} 如不再需要，请手动 git branch -D 删除。[/dim]")


@worktree.command("clean")
@click.option("--force", is_flag=True, help="强制清理（包括有改动的 worktree）")
def worktree_clean(force: bool) -> None:
    """清理失败的 worktree（已失效或无工作区文件）。"""
    repo = _get_repo()

    # 先用 prune 清理元数据
    try:
        args = ["worktree", "prune"]
        if force:
            args.append("--expire=now")
        repo.git.execute(["git"] + args)
    except Exception as exc:
        click.echo(f"prune 失败：{exc}", err=True)
        raise SystemExit(1)

    console.print("[green]✓ 已清理失效的 worktree 元数据。[/green]")

    # 找出 loop/ 开头的分支对应的 worktree（可能是失败的实验）
    loop_branches = [
        b.name for b in repo.branches if b.name.startswith("loop/")
    ]
    if not loop_branches:
        console.print("[dim]未发现 loop/ 开头的实验分支。[/dim]")
        return

    # 列出仍存在的 worktree
    existing_paths: set[str] = set()
    try:
        for block in repo.git.worktree("list", "--porcelain").split("\n\n"):
            for line in block.splitlines():
                if line.startswith("worktree "):
                    existing_paths.add(line[len("worktree "):])
    except Exception:
        pass

    console.print(
        f"[dim]发现 {len(loop_branches)} 个 loop/ 实验分支。"
        "如不再需要，可手动删除：[/dim]"
    )
    for name in loop_branches:
        console.print(f"  [cyan]git branch -D {name}[/cyan]")
