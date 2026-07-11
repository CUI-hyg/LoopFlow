"""模式库冒烟测试。

验证注册表完整性、每个模式的 dry_run / build_loop / to_skill_md / validate。
参数化测试覆盖全部 7 个内置模式。
"""

from __future__ import annotations

import pytest

from loopkits.core.loop import Loop, TrustLevel
from loopkits.patterns.registry import PATTERN_REGISTRY, get, list_patterns

# 所有内置模式名（从注册表动态获取，保证与注册表一致）
_PATTERN_NAMES = [m.name for m in list_patterns()]


def test_registry_has_7_patterns():
    """注册表有 7 个模式。"""
    metas = list_patterns()
    assert len(metas) == 7
    # 验证已知模式名都在
    expected = {
        "daily-triage",
        "pr-babysitter",
        "ci-sweeper",
        "dependency-sweeper",
        "changelog-drafter",
        "post-merge-cleanup",
        "issue-triage",
    }
    actual = {m.name for m in metas}
    assert actual == expected
    # 注册表 dict 也应一致
    assert len(PATTERN_REGISTRY) == 7


@pytest.mark.parametrize("pattern_name", _PATTERN_NAMES)
def test_each_pattern_dry_run(pattern_name):
    """每个模式 dry_run 成功（无凭证环境下返回 mock 结果）。"""
    pattern_cls = get(pattern_name)
    assert pattern_cls is not None, f"模式 {pattern_name} 未注册"
    pattern = pattern_cls()
    result = pattern.dry_run()
    assert isinstance(result, dict)
    assert result.get("dry_run") is True
    assert result.get("pattern") == pattern_name
    # dry_run 结果应非空
    assert len(result) > 0


@pytest.mark.parametrize("pattern_name", _PATTERN_NAMES)
def test_each_pattern_build_loop(pattern_name):
    """每个模式 build_loop 返回 Loop 实例。"""
    pattern_cls = get(pattern_name)
    assert pattern_cls is not None
    pattern = pattern_cls()
    loop = pattern.build_loop()
    assert isinstance(loop, Loop)
    assert loop.config.goal  # 非空


@pytest.mark.parametrize("pattern_name", _PATTERN_NAMES)
def test_each_pattern_to_skill_md(pattern_name):
    """每个模式 to_skill_md 返回非空字符串。"""
    pattern_cls = get(pattern_name)
    assert pattern_cls is not None
    pattern = pattern_cls()
    md = pattern.to_skill_md()
    assert isinstance(md, str)
    assert len(md.strip()) > 0
    # 应包含模式名或 Skill 关键字
    assert pattern_name in md or "Skill" in md or "#" in md


@pytest.mark.parametrize("pattern_name", _PATTERN_NAMES)
def test_each_pattern_validate(pattern_name):
    """每个模式 validate 返回空列表（配置无问题）。"""
    pattern_cls = get(pattern_name)
    assert pattern_cls is not None
    pattern = pattern_cls()
    issues = pattern.validate()
    assert issues == [], f"模式 {pattern_name} 校验失败：{issues}"
