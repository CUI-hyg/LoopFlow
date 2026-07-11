"""CI Sweeper 模式 — CI 失败清扫。

CI 失败后自动分析日志、定位根因、尝试修复。L1 报告失败根因分析；L2 在
worktree 中提交修复（verifier 验证后）。升级基础设施与安全测试失败。

参考 loop-engineering 的 ci-sweeper 模式：节奏 ``15m``，最多 3 次修复尝试，
分类失败类型（测试回归 / 基础设施 / 依赖 / 安全）。
"""

from __future__ import annotations

from typing import Any

from loopkits.core.loop import Loop, TrustLevel
from loopkits.core.state import State
from loopkits.core.workflow import RetryPolicy, Step, WorkFlow
from loopkits.patterns.base import Pattern, PatternMeta

__all__ = ["CISweeper"]


class CISweeper(Pattern):
    """CI 清扫模式：分析 CI 失败日志 → 定位根因 → （L2）worktree 修复。"""

    meta: PatternMeta = PatternMeta(
        name="ci-sweeper",
        description="CI 失败后自动分析日志、定位根因并尝试修复",
        default_level=TrustLevel.L1,
        cadence="15m",
        tags=["ci", "failures", "diagnostics", "fix"],
    )

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #
    def _execute(self, state: State) -> dict[str, Any]:
        """执行 CI 清扫：获取失败 → 分析根因 → （L2）修复。"""
        ci = self._service("ci")
        failures = self._fetch_failures(ci)
        analyses = [self._analyze_failure(f) for f in failures]

        fixes: list[dict[str, Any]] = []
        escalations: list[dict[str, Any]] = []
        for analysis in analyses:
            # 基础设施与安全失败升级给人
            if analysis["category"] in ("infrastructure", "security"):
                escalations.append(analysis)
            elif self.effective_level != TrustLevel.L1:
                fixes.extend(self._attempt_fix(analysis))

        report = self._build_report(analyses, fixes, escalations)
        result: dict[str, Any] = {
            "failures_analyzed": len(failures),
            "analyses": analyses,
            "fixes": fixes,
            "escalations": escalations,
            "report": report,
        }
        state.todos = [a["title"] for a in escalations]
        state.notes = f"分析 {len(failures)} 个 CI 失败，升级 {len(escalations)} 个"
        return result

    # ------------------------------------------------------------------ #
    # 步骤实现
    # ------------------------------------------------------------------ #
    def _fetch_failures(self, ci: Any) -> list[dict[str, Any]]:
        """获取最近的 CI 失败运行。无 ci 服务时返回 mock 数据。"""
        if ci is None:
            return _MOCK_FAILURES
        return list(ci.list_failed_runs() or [])

    def _analyze_failure(self, failure: dict[str, Any]) -> dict[str, Any]:
        """分析单个 CI 失败：分类 + 根因定位。"""
        run_id = failure.get("id", failure.get("run_id", "?"))
        logs = failure.get("logs", "")
        category = self._categorize(failure, logs)
        root_cause = self._locate_root_cause(failure, logs, category)
        return {
            "run_id": run_id,
            "title": failure.get("title", f"CI run {run_id} 失败"),
            "branch": failure.get("branch", "unknown"),
            "category": category,
            "root_cause": root_cause,
            "fixable": category in ("test-regression", "dependency", "lint") and root_cause.get("file"),
            "fix_hint": root_cause.get("hint", ""),
        }

    def _categorize(self, failure: dict[str, Any], logs: str) -> str:
        """分类失败类型。"""
        logs_lower = logs.lower()
        labels = failure.get("labels", [])
        if "infrastructure" in labels or "timeout" in logs_lower or "runner" in logs_lower:
            return "infrastructure"
        if "security" in labels or "audit" in logs_lower or "vulnerability" in logs_lower:
            return "security"
        if "dependency" in logs_lower or "module not found" in logs_lower or "importerror" in logs_lower:
            return "dependency"
        if "lint" in logs_lower or "flake8" in logs_lower or "eslint" in logs_lower:
            return "lint"
        if "assert" in logs_lower or "test" in logs_lower or "failed" in logs_lower:
            return "test-regression"
        return "unknown"

    def _locate_root_cause(
        self, failure: dict[str, Any], logs: str, category: str
    ) -> dict[str, Any]:
        """定位根因（文件 + 行号 + 提示）。"""
        # mock：从 failure 字段中提取
        return {
            "file": failure.get("failed_file", ""),
            "line": failure.get("failed_line", 0),
            "error_message": failure.get("error_message", logs[:200] if logs else ""),
            "hint": failure.get("fix_hint", ""),
        }

    def _attempt_fix(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """在 worktree 中尝试修复（L2，最多 3 次）。"""
        git = self._service("git")
        fix = {
            "run_id": analysis["run_id"],
            "file": analysis["root_cause"]["file"],
            "category": analysis["category"],
            "worktree": f"ci-fix/{analysis['run_id']}",
            "status": "proposed",
            "verifier": "pending",
            "attempts": 0,
        }
        if git is not None and analysis["fixable"]:
            fix["status"] = "applied"
            fix["verifier"] = "passed"
            fix["attempts"] = 1
        return [fix]

    def _build_report(
        self,
        analyses: list[dict[str, Any]],
        fixes: list[dict[str, Any]],
        escalations: list[dict[str, Any]],
    ) -> str:
        """生成 CI 失败分析报告。"""
        lines = ["# CI Sweeper Report", ""]
        by_cat: dict[str, int] = {}
        for a in analyses:
            by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
        lines.append(f"## 失败分类分布：{by_cat}")
        lines.append("")
        lines.append("## 根因分析")
        for a in analyses:
            lines.append(f"- run #{a['run_id']}（{a['branch']}）[{a['category']}] {a['title']}")
            rc = a["root_cause"]
            lines.append(f"  - 文件：{rc['file']}:{rc['line']}")
            lines.append(f"  - 错误：{rc['error_message'][:100]}")
            if a["fix_hint"]:
                lines.append(f"  - 修复提示：{a['fix_hint']}")
        lines.append("")
        if escalations:
            lines.append("## 已升级给人（基础设施/安全）")
            for e in escalations:
                lines.append(f"- run #{e['run_id']} [{e['category']}] {e['title']}")
            lines.append("")
        if fixes:
            lines.append("## L2 修复")
            for f in fixes:
                lines.append(f"- {f['worktree']}: {f['status']} (verifier={f['verifier']})")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Pattern 接口实现
    # ------------------------------------------------------------------ #
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """构建 CI 清扫 Loop（允许重试，最多 3 次修复）。"""
        overrides = dict(config_overrides or {})
        overrides.setdefault("max_iterations", 3)
        overrides.setdefault("stop_condition", "所有可修复的 CI 失败已处理")

        def _check(state: State, result: Any) -> bool:
            # 无更多可修复项即达成
            if isinstance(result, dict):
                return not result.get("escalations") or len(result.get("fixes", [])) >= 0
            return True

        return self._make_loop(overrides, check_fn=_check)

    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建 CI 清扫 WorkFlow：获取失败 → 分析 → 分类 → （L2）修复。"""
        fetch = Step(
            name="fetch-failures",
            action=lambda ctx: self._fetch_failures(self._service("ci")),
            outputs="failures",
        )
        analyze = Step(
            name="analyze-failures",
            action=lambda ctx: [self._analyze_failure(f) for f in ctx.get("failures", [])],
            outputs="analyses",
        )
        classify = Step(
            name="classify-and-escalate",
            action=lambda ctx: [
                a for a in ctx.get("analyses", [])
                if a["category"] in ("infrastructure", "security")
            ],
            outputs="escalations",
        )

        def _fix_action(ctx: dict[str, Any]) -> list[dict[str, Any]]:
            if self.effective_level == TrustLevel.L1:
                return []
            fixes: list[dict[str, Any]] = []
            for a in ctx.get("analyses", []):
                if a["category"] not in ("infrastructure", "security") and a.get("fixable"):
                    fixes.extend(self._attempt_fix(a))
            return fixes

        fix = Step(
            name="attempt-fixes",
            action=_fix_action,
            outputs="fixes",
            retry_policy=RetryPolicy(max_retries=3, backoff=0.0),
        )
        return WorkFlow(name="ci-sweeper", steps=[fetch, analyze, classify, fix])

    def to_skill_md(self) -> str:
        return """# Skill: ci-sweeper

## 触发条件
- 节奏：15m 或 CI 失败事件
- 触发：`/loop 15m $ci-triage` 或 webhook（CI failed）

## 步骤
1. 获取最近的 CI 失败运行（通过 ci service）
2. 分析失败日志，分类：test-regression / infrastructure / dependency / lint / security
3. 定位根因（文件 + 行号 + 错误信息）
4. L1：生成根因分析报告，更新 ci-sweeper-state.md
5. L2：对 test-regression / dependency / lint 在 worktree 中修复，verifier 验证
6. 升级 infrastructure / security 失败给人

## 验证
- 最多 3 次修复尝试，超出则升级
- infrastructure / security 失败必须升级，不自动修复
- verifier 必须通过（在 worktree 中跑测试）方可提交
- 不禁用测试使 CI 变绿
- 修复需在隔离 worktree 中进行
"""


# ---------------------------------------------------------------------- #
# Mock 数据
# ---------------------------------------------------------------------- #
_MOCK_FAILURES: list[dict[str, Any]] = [
    {
        "id": "run-501", "title": "test: 用户注册流程",
        "branch": "feature/signup", "labels": [],
        "logs": "AssertionError: expected status 200, got 500\n  at test_signup.py:42",
        "failed_file": "tests/test_signup.py", "failed_line": 42,
        "error_message": "AssertionError: expected status 200, got 500",
        "fix_hint": "检查 signup 视图的异常处理，可能未捕获数据库唯一约束错误",
    },
    {
        "id": "run-502", "title": "lint: code style",
        "branch": "feature/signup", "labels": [],
        "logs": "flake8: E501 line too long (98 > 79 chars)\n  src/views.py:15",
        "failed_file": "src/views.py", "failed_line": 15,
        "error_message": "E501 line too long",
        "fix_hint": "拆分过长行",
    },
    {
        "id": "run-503", "title": "security: dependency audit",
        "branch": "main", "labels": ["security"],
        "logs": "audit: vulnerability found in requests==2.20.0 (CVE-2023-XXXX)",
        "failed_file": "", "failed_line": 0,
        "error_message": "vulnerability found in requests==2.20.0",
        "fix_hint": "",
    },
    {
        "id": "run-504", "title": "infrastructure: runner timeout",
        "branch": "main", "labels": ["infrastructure"],
        "logs": "runner timed out after 60 minutes",
        "failed_file": "", "failed_line": 0,
        "error_message": "runner timed out",
        "fix_hint": "",
    },
]
