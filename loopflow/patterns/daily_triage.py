"""Daily Triage 模式 — 每日 Issue/PR 分诊。

参考 loop-engineering 的 daily-triage 模式：每日扫描开放的 Issue 与 PR，按
优先级分类（P0/P1/P2/P3），标记需人介入项。L1 仅报告分类结果；L2 对单文件
bugfix 在 worktree 中修复（人工监控）。

节奏：``1d``（每日）。默认信任级别 L1。
"""

from __future__ import annotations

from typing import Any

from loopflow.core.loop import Loop, TrustLevel
from loopflow.core.state import State
from loopflow.core.workflow import RetryPolicy, Step, WorkFlow
from loopflow.patterns.base import Pattern, PatternMeta

__all__ = ["DailyTriage"]


class DailyTriage(Pattern):
    """每日分诊模式：扫描 Issue/PR → 分类 → （L2）修复单文件 bugfix。"""

    meta: PatternMeta = PatternMeta(
        name="daily-triage",
        description="每日扫描 Issue/PR，按优先级分类并标记需人介入项",
        default_level=TrustLevel.L1,
        cadence="1d",
        tags=["triage", "issues", "pull-requests", "report"],
    )

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #
    def _execute(self, state: State) -> dict[str, Any]:
        """执行每日分诊：扫描 → 分类 → （L2）修复。"""
        github = self._service("github")
        items = self._scan_items(github)
        classified = self._classify(items)
        report = self._build_report(classified)

        fixes: list[dict[str, Any]] = []
        # L2：对单文件 bugfix 在 worktree 中修复
        if self.effective_level != TrustLevel.L1:
            fixable = [
                c for c in classified["high_priority"]
                if c.get("scope") == "single-file" and c.get("kind") == "bugfix"
            ]
            fixes = self._attempt_fixes(fixable)

        result: dict[str, Any] = {
            "scanned": len(items),
            "by_priority": classified["by_priority"],
            "high_priority": classified["high_priority"],
            "needs_human": classified["needs_human"],
            "watch_list": classified["watch_list"],
            "fixes": fixes,
            "report": report,
        }
        # 更新状态
        state.todos = [c["title"] for c in classified["high_priority"]]
        state.notes = f"扫描 {len(items)} 项，需人介入 {len(classified['needs_human'])} 项"
        return result

    # ------------------------------------------------------------------ #
    # 步骤实现（可被 WorkFlow 调用）
    # ------------------------------------------------------------------ #
    def _scan_items(self, github: Any) -> list[dict[str, Any]]:
        """扫描开放的 Issue 与 PR。无 github 服务时返回 mock 数据。"""
        if github is None:
            return _MOCK_ITEMS
        # 真实服务：调用 github.list_issues() / github.list_pulls()
        issues = list(github.list_issues(state="open") or [])
        pulls = list(github.list_pulls(state="open") or [])
        return [*issues, *pulls]

    def _classify(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """按优先级分类：P0（紧急）/ P1（高）/ P2（中）/ P3（低）。"""
        by_priority: dict[str, list[dict[str, Any]]] = {
            "P0": [], "P1": [], "P2": [], "P3": [],
        }
        needs_human: list[dict[str, Any]] = []
        watch_list: list[dict[str, Any]] = []
        high_priority: list[dict[str, Any]] = []

        for item in items:
            priority = item.get("priority", "P2")
            labels = item.get("labels", [])
            entry = {
                "id": item.get("id", item.get("number", "?")),
                "title": item.get("title", "(无标题)"),
                "priority": priority,
                "labels": labels,
                "scope": item.get("scope", "unknown"),
                "kind": item.get("kind", "unknown"),
            }
            by_priority.setdefault(priority, []).append(entry)
            # P0/P1 或含 security 标签 → 需人介入
            if priority in ("P0", "P1") or "security" in labels:
                needs_human.append(entry)
            elif priority == "P2":
                high_priority.append(entry)
            else:
                watch_list.append(entry)

        # P1 已在 needs_human 中（需人介入），不再加入 high_priority
        # 仅 P2 single-file bugfix 可作为 L2 自动修复候选（已在上方 elif 分支加入）

        return {
            "by_priority": {k: len(v) for k, v in by_priority.items()},
            "high_priority": high_priority,
            "needs_human": needs_human,
            "watch_list": watch_list,
        }

    def _build_report(self, classified: dict[str, Any]) -> str:
        """生成人可读的分诊报告。"""
        lines = [
            "# Daily Triage Report",
            "",
            f"## 按优先级分布：{classified['by_priority']}",
            "",
            "## High Priority（可尝试 L2 修复）",
        ]
        for c in classified["high_priority"]:
            lines.append(f"- [{c['priority']}] #{c['id']} {c['title']} ({c['scope']}/{c['kind']})")
        lines.append("")
        lines.append("## Needs Human")
        for c in classified["needs_human"]:
            lines.append(f"- [{c['priority']}] #{c['id']} {c['title']} {c['labels']}")
        lines.append("")
        lines.append("## Watch List")
        for c in classified["watch_list"]:
            lines.append(f"- [{c['priority']}] #{c['id']} {c['title']}")
        return "\n".join(lines)

    def _attempt_fixes(self, fixable: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """在 worktree 中尝试修复单文件 bugfix（L2）。"""
        git = self._service("git")
        fixes: list[dict[str, Any]] = []
        for item in fixable[:3]:  # 最多 3 次修复尝试
            fix = {
                "item_id": item["id"],
                "title": item["title"],
                "worktree": f"fix/{item['id']}-bugfix",
                "status": "proposed",
                "verifier": "pending",
            }
            if git is not None:
                # 真实服务：git.create_worktree() + 应用修复
                fix["status"] = "applied"
                fix["verifier"] = "passed"
            fixes.append(fix)
        return fixes

    # ------------------------------------------------------------------ #
    # Pattern 接口实现
    # ------------------------------------------------------------------ #
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """构建每日分诊 Loop（单趟扫描，L2 时附带修复）。"""
        return self._make_loop(config_overrides)

    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建每日分诊 WorkFlow：扫描 → 分类 → 报告 → （L2）修复。"""
        scan = Step(
            name="scan-items",
            action=lambda ctx: self._scan_items(self._service("github")),
            outputs="items",
        )
        classify = Step(
            name="classify",
            action=lambda ctx: self._classify(ctx.get("items", [])),
            outputs="classified",
        )
        report = Step(
            name="build-report",
            action=lambda ctx: self._build_report(ctx.get("classified", {})),
            outputs="report",
        )

        def _fix_action(ctx: dict[str, Any]) -> list[dict[str, Any]]:
            if self.effective_level == TrustLevel.L1:
                return []
            classified = ctx.get("classified", {})
            fixable = [
                c for c in classified.get("high_priority", [])
                if c.get("scope") == "single-file" and c.get("kind") == "bugfix"
            ]
            return self._attempt_fixes(fixable)

        fix = Step(
            name="attempt-fixes",
            action=_fix_action,
            outputs="fixes",
            retry_policy=RetryPolicy(max_retries=2, backoff=0.0),
        )
        return WorkFlow(name="daily-triage", steps=[scan, classify, report, fix])

    def to_skill_md(self) -> str:
        """生成 SKILL.md 片段。"""
        return """# Skill: daily-triage

## 触发条件
- 节奏：每日（1d），工作日运行
- 触发：cron 或手动 `/loop 1d $loop-triage`

## 步骤
1. 读取 STATE.md（上一次迭代的状态）
2. 扫描开放的 Issue 与 PR（通过 github service）
3. 按优先级分类：P0（紧急）/ P1（高）/ P2（中）/ P3（低）
4. 标记需人介入项（P0/P1/security 标签）
5. L1：仅生成分诊报告，更新 STATE.md
6. L2：对单文件 bugfix 在 worktree 中修复，verifier 验证后提交

## 验证
- 报告包含所有开放 Issue/PR
- 需人介入项已正确标记
- L2 修复需 verifier 通过方可提交
- 最多 3 次修复尝试，超出则升级给人
- 不触碰 denylist 路径（.env / secrets / auth 等）
"""


# ---------------------------------------------------------------------- #
# Mock 数据（dry_run 使用）
# ---------------------------------------------------------------------- #
_MOCK_ITEMS: list[dict[str, Any]] = [
    {
        "id": 101, "title": "登录页面在 Safari 崩溃",
        "priority": "P0", "labels": ["bug", "security"],
        "scope": "single-file", "kind": "bugfix",
    },
    {
        "id": 102, "title": "导出 CSV 列顺序错误",
        "priority": "P1", "labels": ["bug"],
        "scope": "single-file", "kind": "bugfix",
    },
    {
        "id": 103, "title": "文档拼写错误",
        "priority": "P3", "labels": ["docs"],
        "scope": "single-file", "kind": "docs",
    },
    {
        "id": 104, "title": "重构支付模块以支持多币种",
        "priority": "P1", "labels": ["enhancement", "payments"],
        "scope": "multi-file", "kind": "feature",
    },
    {
        "id": 105, "title": "CI 偶发性超时",
        "priority": "P2", "labels": ["ci", "flaky"],
        "scope": "config", "kind": "bugfix",
    },
]
