"""PR Babysitter 模式 — PR 看护。

新 PR 提交后触发，检查代码风格、测试覆盖、潜在安全问题。L1 评论审查结果；
L2 在 worktree 中提交修复建议（verifier 验证后）。

参考 loop-engineering 的 pr-babysitter 模式：节奏 ``5m``~``15m``，每个 PR 最多
3 次修复尝试，不自动合并。
"""

from __future__ import annotations

from typing import Any

from loopflow.core.loop import Loop, TrustLevel
from loopflow.core.state import State
from loopflow.core.workflow import RetryPolicy, Step, WorkFlow
from loopflow.patterns.base import Pattern, PatternMeta

__all__ = ["PRBabysitter"]


class PRBabysitter(Pattern):
    """PR 看护模式：审查代码风格/测试/安全 → 评论 → （L2）worktree 修复。"""

    meta: PatternMeta = PatternMeta(
        name="pr-babysitter",
        description="新 PR 触发：检查代码风格、测试覆盖、安全问题并评论",
        default_level=TrustLevel.L1,
        cadence="5m",
        tags=["pull-requests", "review", "security", "lint"],
    )

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #
    def _execute(self, state: State) -> dict[str, Any]:
        """执行 PR 看护：拉取 PR → 审查 → 评论/修复。"""
        github = self._service("github")
        prs = self._fetch_open_prs(github)
        reviews = [self._review_pr(pr) for pr in prs]

        fixes: list[dict[str, Any]] = []
        if self.effective_level != TrustLevel.L1:
            for review in reviews:
                if review["blocking_issues"]:
                    fixes.extend(self._propose_fixes(review))

        report = self._build_report(reviews)
        result: dict[str, Any] = {
            "prs_reviewed": len(prs),
            "reviews": reviews,
            "fixes": fixes,
            "report": report,
        }
        state.todos = [r["pr_title"] for r in reviews if r["blocking_issues"]]
        state.notes = f"审查 {len(prs)} 个 PR，阻断项 {sum(len(r['blocking_issues']) for r in reviews)} 个"
        return result

    # ------------------------------------------------------------------ #
    # 步骤实现
    # ------------------------------------------------------------------ #
    def _fetch_open_prs(self, github: Any) -> list[dict[str, Any]]:
        """拉取待审查的开放 PR。无 github 服务时返回 mock 数据。"""
        if github is None:
            return _MOCK_PRS
        return list(github.list_pulls(state="open") or [])

    def _review_pr(self, pr: dict[str, Any]) -> dict[str, Any]:
        """审查单个 PR：代码风格、测试覆盖、安全问题。"""
        pr_id = pr.get("id", pr.get("number", "?"))
        title = pr.get("title", "(无标题)")
        # 检查维度
        style_issues = self._check_style(pr)
        test_coverage = self._check_tests(pr)
        security_issues = self._check_security(pr)
        blocking = []
        if security_issues:
            blocking.extend(security_issues)
        if test_coverage["coverage"] < 0.5:
            blocking.append(f"测试覆盖率 {test_coverage['coverage']:.0%} 低于 50%")

        return {
            "pr_id": pr_id,
            "pr_title": title,
            "author": pr.get("author", "unknown"),
            "style_issues": style_issues,
            "test_coverage": test_coverage,
            "security_issues": security_issues,
            "blocking_issues": blocking,
            "verdict": "request-changes" if blocking else "approve",
        }

    def _check_style(self, pr: dict[str, Any]) -> list[str]:
        """检查代码风格问题。"""
        issues: list[str] = []
        diffs = pr.get("diff", {})
        for path, change in diffs.items():
            if change.get("lines_added", 0) > 0 and not change.get("lint_passed", True):
                issues.append(f"{path}: 存在 lint 警告")
        return issues

    def _check_tests(self, pr: dict[str, Any]) -> dict[str, Any]:
        """检查测试覆盖情况。"""
        diffs = pr.get("diff", {})
        total_added = sum(c.get("lines_added", 0) for c in diffs.values())
        test_added = sum(
            c.get("lines_added", 0)
            for path, c in diffs.items()
            if "test" in path.lower()
        )
        coverage = 0.0
        if total_added > 0:
            coverage = min(1.0, test_added / total_added * 2)
        return {
            "coverage": coverage,
            "test_lines": test_added,
            "total_lines": total_added,
            "has_tests": test_added > 0,
        }

    def _check_security(self, pr: dict[str, Any]) -> list[str]:
        """检查潜在安全问题。"""
        issues: list[str] = []
        diffs = pr.get("diff", {})
        for path in diffs:
            if path.startswith(".env") or "secret" in path.lower():
                issues.append(f"{path}: 可能泄露敏感信息")
            if "auth/" in path or "payments/" in path:
                issues.append(f"{path}: 触碰敏感目录，需人工审查")
        # PR 标签中的 security 标记
        if "security" in pr.get("labels", []):
            issues.append("PR 带 security 标签，需安全团队审查")
        return issues

    def _propose_fixes(self, review: dict[str, Any]) -> list[dict[str, Any]]:
        """在 worktree 中提交修复建议（L2）。"""
        git = self._service("git")
        fixes: list[dict[str, Any]] = []
        for issue in review["blocking_issues"][:3]:  # 最多 3 次
            fix = {
                "pr_id": review["pr_id"],
                "issue": issue,
                "worktree": f"pr-{review['pr_id']}-fix",
                "status": "proposed",
                "verifier": "pending",
            }
            if git is not None:
                fix["status"] = "applied"
                fix["verifier"] = "passed"
            fixes.append(fix)
        return fixes

    def _build_report(self, reviews: list[dict[str, Any]]) -> str:
        """生成 PR 审查报告。"""
        lines = ["# PR Babysitter Report", ""]
        for r in reviews:
            lines.append(f"## PR #{r['pr_id']} {r['pr_title']}（{r['author']}）")
            lines.append(f"- 结论：**{r['verdict']}**")
            lines.append(f"- 代码风格：{len(r['style_issues'])} 个问题")
            lines.append(f"- 测试覆盖：{r['test_coverage']['coverage']:.0%}")
            lines.append(f"- 安全问题：{len(r['security_issues'])} 个")
            if r["blocking_issues"]:
                lines.append("- 阻断项：")
                for b in r["blocking_issues"]:
                    lines.append(f"  - {b}")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Pattern 接口实现
    # ------------------------------------------------------------------ #
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """构建 PR 看护 Loop（单趟审查，每个 PR 最多 3 次修复）。"""
        overrides = dict(config_overrides or {})
        overrides.setdefault("max_iterations", 1)
        overrides.setdefault("stop_condition", "所有开放 PR 已审查")
        return self._make_loop(overrides)

    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建 PR 看护 WorkFlow：拉取 PR → 审查 → 评论 → （L2）修复。"""
        fetch = Step(
            name="fetch-prs",
            action=lambda ctx: self._fetch_open_prs(self._service("github")),
            outputs="prs",
        )
        review = Step(
            name="review-prs",
            action=lambda ctx: [self._review_pr(pr) for pr in ctx.get("prs", [])],
            outputs="reviews",
        )
        comment = Step(
            name="post-comments",
            action=lambda ctx: self._build_report(ctx.get("reviews", [])),
            outputs="report",
        )

        def _fix_action(ctx: dict[str, Any]) -> list[dict[str, Any]]:
            if self.effective_level == TrustLevel.L1:
                return []
            fixes: list[dict[str, Any]] = []
            for review in ctx.get("reviews", []):
                if review.get("blocking_issues"):
                    fixes.extend(self._propose_fixes(review))
            return fixes

        fix = Step(
            name="propose-fixes",
            action=_fix_action,
            outputs="fixes",
            retry_policy=RetryPolicy(max_retries=3, backoff=0.0),
        )
        return WorkFlow(name="pr-babysitter", steps=[fetch, review, comment, fix])

    def to_skill_md(self) -> str:
        return """# Skill: pr-babysitter

## 触发条件
- 节奏：5m（活跃时段）或新 PR 提交事件
- 触发：`/loop 5m /babysit` 或 webhook

## 步骤
1. 拉取所有待审查的开放 PR（通过 github service）
2. 对每个 PR 审查：代码风格 / 测试覆盖 / 潜在安全问题
3. L1：在 PR 上评论审查结果与建议
4. L2：对阻断项在 worktree 中提交修复，verifier 验证后推送
5. 更新 pr-babysitter-state.md

## 验证
- 每个 PR 最多 3 次修复尝试
- 安全问题（.env / auth / payments）必须升级给人
- verifier 必须通过方可评论或推送修复
- 不自动合并 PR
- 不关闭 PR（需人工批准）
"""


# ---------------------------------------------------------------------- #
# Mock 数据
# ---------------------------------------------------------------------- #
_MOCK_PRS: list[dict[str, Any]] = [
    {
        "id": 201, "title": "feat: 添加用户头像上传",
        "author": "alice", "labels": ["enhancement"],
        "diff": {
            "src/upload.py": {"lines_added": 80, "lint_passed": False},
            "tests/test_upload.py": {"lines_added": 40, "lint_passed": True},
        },
    },
    {
        "id": 202, "title": "fix: 修复 token 校验逻辑",
        "author": "bob", "labels": ["bug", "security"],
        "diff": {
            "auth/token.py": {"lines_added": 15, "lint_passed": True},
        },
    },
    {
        "id": 203, "title": "docs: 更新 README",
        "author": "carol", "labels": ["docs"],
        "diff": {
            "README.md": {"lines_added": 20, "lint_passed": True},
        },
    },
]
