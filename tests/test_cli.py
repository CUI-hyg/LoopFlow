"""CLI 集成测试。

使用 click.testing.CliRunner 测试 loopflow CLI 子命令：
init / audit / run / state / skill / service。
所有测试在 tmp_path 中运行，不依赖外部服务。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from loopflow.cli.audit import audit, run_audit
from loopflow.cli.init import init
from loopflow.cli.run import run as run_cmd
from loopflow.cli.service import service
from loopflow.cli.skill import skill
from loopflow.cli.state import state as state_cmd
from loopflow.core.state import State


@pytest.fixture
def runner():
    """CliRunner fixture。"""
    return CliRunner()


# ====================================================================== #
# init
# ====================================================================== #
def test_init_creates_files(runner, tmp_path):
    """init 生成所有脚手架文件。"""
    result = runner.invoke(
        init,
        [
            str(tmp_path),
            "--pattern",
            "daily-triage",
            "--tool",
            "claude",
            "--level",
            "L1",
        ],
    )
    assert result.exit_code == 0, f"init 失败：{result.output}"

    # 核心文件应存在
    assert (tmp_path / "LOOP.md").is_file()
    assert (tmp_path / "STATE.md").is_file()
    assert (tmp_path / "loop-budget.yaml").is_file()
    assert (tmp_path / "loop-constraints.md").is_file()

    # claude 工具应生成技能文件
    skill_md = tmp_path / ".claude" / "skills" / "loop-triage" / "SKILL.md"
    assert skill_md.is_file()

    # LOOP.md 内容应包含模式名与级别
    loop_md = (tmp_path / "LOOP.md").read_text(encoding="utf-8")
    assert "daily-triage" in loop_md
    assert "L1" in loop_md

    # loop-budget.yaml 应含预算配置
    budget_yaml = (tmp_path / "loop-budget.yaml").read_text(encoding="utf-8")
    assert "daily_cap" in budget_yaml


# ====================================================================== #
# audit
# ====================================================================== #
def test_audit_scores(runner, tmp_path):
    """audit 输出 0-100 评分。"""
    # 空目录评分应为 0（无任何文件）
    score, details = run_audit(tmp_path)
    assert 0 <= score <= 100
    assert isinstance(details, list)
    assert len(details) > 0

    # 用 init 生成文件后评分应提升
    runner.invoke(init, [str(tmp_path)])
    score_after, _ = run_audit(tmp_path)
    assert score_after > score

    # CLI 命令应正常运行
    result = runner.invoke(audit, [str(tmp_path)])
    assert result.exit_code == 0


# ====================================================================== #
# run --dry-run
# ====================================================================== #
def test_run_dry_run(runner):
    """run --dry-run 成功（使用 mock 数据）。"""
    result = runner.invoke(run_cmd, ["daily-triage", "--dry-run"])
    assert result.exit_code == 0, f"dry-run 失败：{result.output}"
    # 输出应包含 dry-run 标识
    assert "dry" in result.output.lower() or "模拟" in result.output


def test_run_dry_run_all_patterns(runner):
    """所有模式 dry-run 均成功。"""
    from loopflow.patterns.registry import list_patterns

    for meta in list_patterns():
        result = runner.invoke(run_cmd, [meta.name, "--dry-run"])
        assert result.exit_code == 0, f"{meta.name} dry-run 失败：{result.output}"


# ====================================================================== #
# state show / pause / resume
# ====================================================================== #
def test_state_commands(runner, tmp_path):
    """state show / pause / resume 子命令。"""
    state_path = tmp_path / "STATE.md"
    # 先创建初始状态
    State(goal="状态测试", iteration=2).save(state_path)

    # show
    result = runner.invoke(state_cmd, ["show", "--path", str(state_path)])
    assert result.exit_code == 0, f"state show 失败：{result.output}"
    assert "状态测试" in result.output or "ACTIVE" in result.output.upper() or "状态" in result.output

    # pause
    result = runner.invoke(state_cmd, ["pause", "--path", str(state_path)])
    assert result.exit_code == 0, f"state pause 失败：{result.output}"
    # 验证已写入暂停标志
    loaded = State.load(state_path)
    assert loaded.is_paused() is True

    # resume
    result = runner.invoke(state_cmd, ["resume", "--path", str(state_path)])
    assert result.exit_code == 0, f"state resume 失败：{result.output}"
    loaded = State.load(state_path)
    assert loaded.is_paused() is False


# ====================================================================== #
# skill export
# ====================================================================== #
def test_skill_export(runner, tmp_path):
    """skill export 生成 SKILL.md 文件。"""
    result = runner.invoke(
        skill,
        [
            "export",
            "--pattern",
            "daily-triage",
            "--target",
            "claude-code",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, f"skill export 失败：{result.output}"

    # 应生成 SKILL.md 文件
    skill_files = list(tmp_path.rglob("SKILL.md"))
    assert len(skill_files) > 0, "未生成 SKILL.md"

    # 内容应非空且包含模式名
    content = skill_files[0].read_text(encoding="utf-8")
    assert len(content) > 0
    assert "daily-triage" in content


def test_skill_list(runner):
    """skill list 列出所有模式。"""
    result = runner.invoke(skill, ["list"])
    assert result.exit_code == 0
    assert "daily-triage" in result.output


# ====================================================================== #
# service list
# ====================================================================== #
def test_service_list(runner):
    """service list 无异常（即使无已注册服务）。"""
    result = runner.invoke(service, ["list"])
    assert result.exit_code == 0, f"service list 失败：{result.output}"
