"""循环模式库（Code 模式）。

提供 7 个可复用的 Loop Engineering 循环模式：

- :class:`DailyTriage` — 每日 Issue/PR 分诊
- :class:`PRBabysitter` — PR 看护（代码风格/测试/安全审查）
- :class:`CISweeper` — CI 失败清扫（根因分析 + 修复）
- :class:`DependencySweeper` — 依赖升级清扫（patch 自动 / minor+major 评估）
- :class:`ChangelogDrafter` — 变更日志草案生成
- :class:`PostMergeCleanup` — 合并后清理（分支/Issue）
- :class:`IssueTriage` — 新 Issue 分诊（标签/优先级/回复）

每个模式继承 :class:`Pattern`，提供 ``build_loop()`` / ``build_workflow()``
/ ``dry_run()`` / ``to_skill_md()`` 等方法。模式通过 ``service_provider``
抽象外部服务依赖，``dry_run()`` 无需凭证即可运行。

用法::

    from loopkits.patterns import DailyTriage, list_patterns

    for meta in list_patterns():
        print(meta.name, meta.description)

    pattern = DailyTriage()
    result = pattern.dry_run()  # 无需凭证
    loop = pattern.build_loop()  # 构建 Loop
"""

from loopkits.patterns.base import Pattern, PatternMeta
from loopkits.patterns.changelog_drafter import ChangelogDrafter
from loopkits.patterns.ci_sweeper import CISweeper
from loopkits.patterns.daily_triage import DailyTriage
from loopkits.patterns.dependency_sweeper import DependencySweeper
from loopkits.patterns.issue_triage import IssueTriage
from loopkits.patterns.post_merge_cleanup import PostMergeCleanup
from loopkits.patterns.pr_babysitter import PRBabysitter
from loopkits.patterns.registry import (
    PATTERN_REGISTRY,
    get,
    list_patterns,
    register,
)

__all__ = [
    # 基类
    "Pattern",
    "PatternMeta",
    # 7 个模式
    "DailyTriage",
    "PRBabysitter",
    "CISweeper",
    "DependencySweeper",
    "ChangelogDrafter",
    "PostMergeCleanup",
    "IssueTriage",
    # 注册表
    "PATTERN_REGISTRY",
    "register",
    "get",
    "list_patterns",
]
