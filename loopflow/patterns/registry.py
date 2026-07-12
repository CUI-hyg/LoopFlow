"""模式注册表。

集中管理所有已注册的循环模式，提供按名获取与列举元数据的能力。内置 7 个
Code 模式循环模式（daily-triage / pr-babysitter / ci-sweeper /
dependency-sweeper / changelog-drafter / post-merge-cleanup / issue-triage）。

用法::

    from loopflow.patterns import PATTERN_REGISTRY, list_patterns, get

    # 列出所有模式元数据
    for meta in list_patterns():
        print(meta.name, meta.description)

    # 按名获取模式类
    DailyTriage = get("daily-triage")
    loop = DailyTriage().build_loop()
"""

from __future__ import annotations

from loopflow.patterns.base import Pattern, PatternMeta
from loopflow.patterns.changelog_drafter import ChangelogDrafter
from loopflow.patterns.ci_sweeper import CISweeper
from loopflow.patterns.daily_triage import DailyTriage
from loopflow.patterns.dependency_sweeper import DependencySweeper
from loopflow.patterns.issue_triage import IssueTriage
from loopflow.patterns.post_merge_cleanup import PostMergeCleanup
from loopflow.patterns.pr_babysitter import PRBabysitter

__all__ = [
    "PATTERN_REGISTRY",
    "register",
    "get",
    "list_patterns",
]


def _build_default_registry() -> dict[str, type[Pattern]]:
    """构建默认注册表，注册内置 7 个模式。"""
    registry: dict[str, type[Pattern]] = {}
    for pattern_cls in (
        DailyTriage,
        PRBabysitter,
        CISweeper,
        DependencySweeper,
        ChangelogDrafter,
        PostMergeCleanup,
        IssueTriage,
    ):
        register(pattern_cls, registry=registry)
    return registry


def register(
    pattern_cls: type[Pattern],
    *,
    registry: dict[str, type[Pattern]] | None = None,
) -> None:
    """注册一个模式类。

    Args:
        pattern_cls: :class:`Pattern` 子类。
        registry: 目标注册表；为 None 则使用全局 :data:`PATTERN_REGISTRY`。
    """
    target = registry if registry is not None else PATTERN_REGISTRY
    name = pattern_cls.meta.name
    target[name] = pattern_cls


def get(name: str) -> type[Pattern] | None:
    """按名获取模式类；不存在返回 None。"""
    return PATTERN_REGISTRY.get(name)


def list_patterns() -> list[PatternMeta]:
    """列出所有已注册模式的元数据（按注册顺序）。"""
    return [cls.meta for cls in PATTERN_REGISTRY.values()]


# 全局注册表（模块加载时初始化内置 7 个模式）
PATTERN_REGISTRY: dict[str, type[Pattern]] = _build_default_registry()
