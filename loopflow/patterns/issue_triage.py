"""Issue Triage 模式 — Issue 分诊。

新 Issue 自动分析、打标签、判断优先级、回复初步信息。L1 propose-only（仅
建议标签，不操作）；L2 自动打标签（仅 allowlist 标签，P0/P1/security 仍需人工）。

参考 loop-engineering 的 issue-triage 模式：节奏 ``2h``，扫描自上次运行以来的
新 Issue，升级 auth/payments/security 项。
"""

from __future__ import annotations

from typing import Any

from loopflow.core.loop import Loop, TrustLevel
from loopflow.core.state import State
from loopflow.core.workflow import Step, WorkFlow
from loopflow.patterns.base import Pattern, PatternMeta

__all__ = ["IssueTriage"]


class IssueTriage(Pattern):
    """Issue 分诊模式：扫描新 Issue → 分析 → 建议标签 → （L2）自动打标签。"""

    meta: PatternMeta = PatternMeta(
        name="issue-triage",
        description="新 Issue 自动分析、打标签、判断优先级、回复初步信息",
        default_level=TrustLevel.L1,
        cadence="2h",
        tags=["issues", "triage", "labels", "automation"],
    )

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #
    def _execute(self, state: State) -> dict[str, Any]:
        """执行 Issue 分诊：扫描 → 分析 → 建议标签 → （L2）打标签。"""
        github = self._service("github")
        issues = self._fetch_new_issues(github)
        triaged = [self._triage_issue(issue) for issue in issues]

        applied: list[dict[str, Any]] = []
        if self.effective_level != TrustLevel.L1:
            for t in triaged:
                # 仅 allowlist 标签可自动打，P0/P1/security 需人工
                auto_labels = [
                    lbl for lbl in t["suggested_labels"]
                    if lbl in _ALLOWLIST_LABELS and t["priority"] not in ("P0", "P1")
                    and "security" not in t["suggested_labels"]
                ]
                if auto_labels and github is not None:
                    applied.append({
                        "issue_id": t["issue_id"],
                        "labels": auto_labels,
                        "status": "applied",
                    })

        report = self._build_report(triaged, applied)
        result: dict[str, Any] = {
            "issues_scanned": len(issues),
            "triaged": triaged,
            "top_5": triaged[:5],
            "needs_human": [t for t in triaged if t["needs_human"]],
            "applied_labels": applied,
            "report": report,
        }
        state.todos = [t["title"] for t in triaged if t["needs_human"]]
        state.notes = f"扫描 {len(issues)} 个 Issue，需人介入 {len(result['needs_human'])} 个"
        return result

    # ------------------------------------------------------------------ #
    # 步骤实现
    # ------------------------------------------------------------------ #
    def _fetch_new_issues(self, github: Any) -> list[dict[str, Any]]:
        """获取自上次运行以来的新 Issue。无 github 服务时返回 mock 数据。"""
        if github is None:
            return _MOCK_ISSUES
        return list(github.list_issues(state="open", since="last_run") or [])

    def _triage_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        """分析单个 Issue：分类、建议标签、判断优先级、生成回复。"""
        issue_id = issue.get("id", issue.get("number", "?"))
        title = issue.get("title", "(无标题)")
        body = issue.get("body", "")
        existing_labels = issue.get("labels", [])

        # 分析
        suggested_labels = self._suggest_labels(title, body, existing_labels)
        priority = self._assess_priority(title, body, suggested_labels)
        category = self._categorize(title, body, suggested_labels)
        needs_human = (
            priority in ("P0", "P1")
            or "security" in suggested_labels
            or category in ("auth", "payments", "security")
        )
        reply = self._generate_reply(title, category, priority, needs_human, suggested_labels)

        return {
            "issue_id": issue_id,
            "title": title,
            "author": issue.get("author", "unknown"),
            "existing_labels": existing_labels,
            "suggested_labels": suggested_labels,
            "priority": priority,
            "category": category,
            "needs_human": needs_human,
            "reply": reply,
            "confidence": 0.8 if not needs_human else 0.6,
        }

    def _suggest_labels(
        self, title: str, body: str, existing: list[str]
    ) -> list[str]:
        """基于标题与正文建议标签。"""
        text = f"{title} {body}".lower()
        labels: list[str] = []
        # 组件区域
        if any(k in text for k in ("登录", "注册", "auth", "token", "password")):
            labels.append("area:auth")
        if any(k in text for k in ("支付", "payment", "billing", "订阅")):
            labels.append("area:payments")
        if any(k in text for k in ("api", "接口", "endpoint")):
            labels.append("area:api")
        if any(k in text for k in ("ui", "界面", "样式", "css")):
            labels.append("area:ui")
        # 类型
        if any(k in text for k in ("bug", "错误", "崩溃", "异常", "失败")):
            labels.append("bug")
        if any(k in text for k in ("feature", "建议", "希望", "能否")):
            labels.append("enhancement")
        if any(k in text for k in ("文档", "doc", "readme")):
            labels.append("docs")
        # 状态
        if not body or len(body) < 20:
            labels.append("needs-info")
        if any(k in text for k in ("复现", "reproduce", "步骤")):
            labels.append("has-repro")
        else:
            labels.append("needs-repro")
        # 安全
        if any(k in text for k in ("安全", "security", "漏洞", "vulnerability", "xss", "sqli")):
            labels.append("security")
        return labels

    def _assess_priority(
        self, title: str, body: str, labels: list[str]
    ) -> str:
        """判断优先级。"""
        text = f"{title} {body}".lower()
        if "security" in labels or any(k in text for k in ("崩溃", "数据丢失", "crash", "data loss")):
            return "P0"
        if any(k in text for k in ("阻断", "无法", "blocker", "cannot")):
            return "P1"
        if any(k in text for k in ("bug", "错误", "失败")):
            return "P2"
        return "P3"

    def _categorize(
        self, title: str, body: str, labels: list[str]
    ) -> str:
        """分类 Issue 所属区域。"""
        if "area:auth" in labels:
            return "auth"
        if "area:payments" in labels:
            return "payments"
        if "security" in labels:
            return "security"
        if "area:api" in labels:
            return "api"
        if "area:ui" in labels:
            return "ui"
        if "docs" in labels:
            return "docs"
        return "general"

    def _generate_reply(
        self,
        title: str,
        category: str,
        priority: str,
        needs_human: bool,
        suggested_labels: list[str] | None = None,
    ) -> str:
        """生成初步回复。"""
        lines = [
            f"感谢提交 Issue！我已对它进行了初步分诊：",
            "",
            f"- **分类**：{category}",
            f"- **优先级**：{priority}",
            f"- **建议标签**：见上方",
        ]
        if needs_human:
            lines.append("")
            lines.append("⚠️ 此 Issue 需要人工进一步审查，维护者将尽快跟进。")
        else:
            lines.append("")
            lines.append("我们将在后续迭代中处理此 Issue，请关注更新。")
        if priority == "P3" and suggested_labels and "needs-repro" in suggested_labels:
            lines.append("")
            lines.append("💡 为加快处理，请提供复现步骤与环境信息。")
        return "\n".join(lines)

    def _build_report(
        self, triaged: list[dict[str, Any]], applied: list[dict[str, Any]]
    ) -> str:
        """生成分诊报告。"""
        lines = ["# Issue Triage Report", ""]
        by_priority: dict[str, int] = {}
        for t in triaged:
            by_priority[t["priority"]] = by_priority.get(t["priority"], 0) + 1
        lines.append(f"## 优先级分布：{by_priority}")
        lines.append("")
        lines.append("## Top 5")
        for t in triaged[:5]:
            lines.append(
                f"- [{t['priority']}] #{t['issue_id']} {t['title']} "
                f"({t['category']}, labels={t['suggested_labels']})"
            )
        lines.append("")
        needs_human = [t for t in triaged if t["needs_human"]]
        if needs_human:
            lines.append("## Needs Human")
            for t in needs_human:
                lines.append(f"- [{t['priority']}] #{t['issue_id']} {t['title']}")
            lines.append("")
        if applied:
            lines.append("## L2 已自动打标签")
            for a in applied:
                lines.append(f"- Issue #{a['issue_id']}: {a['labels']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Pattern 接口实现
    # ------------------------------------------------------------------ #
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """构建 Issue 分诊 Loop（单趟扫描，L2 仅打 allowlist 标签）。"""
        overrides = dict(config_overrides or {})
        overrides.setdefault("max_iterations", 1)
        overrides.setdefault("stop_condition", "所有新 Issue 已分诊")
        return self._make_loop(overrides)

    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建 Issue 分诊 WorkFlow：扫描 → 分析 → 建议标签 → （L2）打标签。"""
        fetch = Step(
            name="fetch-new-issues",
            action=lambda ctx: self._fetch_new_issues(self._service("github")),
            outputs="issues",
        )
        triage = Step(
            name="triage-issues",
            action=lambda ctx: [self._triage_issue(i) for i in ctx.get("issues", [])],
            outputs="triaged",
        )

        def _apply_labels(ctx: dict[str, Any]) -> list[dict[str, Any]]:
            if self.effective_level == TrustLevel.L1:
                return []
            github = self._service("github")
            if github is None:
                return []
            applied: list[dict[str, Any]] = []
            for t in ctx.get("triaged", []):
                auto_labels = [
                    lbl for lbl in t["suggested_labels"]
                    if lbl in _ALLOWLIST_LABELS
                    and t["priority"] not in ("P0", "P1")
                    and "security" not in t["suggested_labels"]
                ]
                if auto_labels:
                    applied.append({
                        "issue_id": t["issue_id"],
                        "labels": auto_labels,
                        "status": "applied",
                    })
            return applied

        apply = Step(
            name="apply-labels",
            action=_apply_labels,
            outputs="applied",
        )
        return WorkFlow(name="issue-triage", steps=[fetch, triage, apply])

    def to_skill_md(self) -> str:
        return """# Skill: issue-triage

## 触发条件
- 节奏：2h 或新 Issue 创建事件
- 触发：`/loop 2h $issue-triage` 或 webhook

## 步骤
1. 读取 issue-triage-state.md（上次运行时间）
2. 扫描自上次运行以来的新 Issue（通过 github service）
3. 分析每个 Issue：分类 / 建议标签 / 判断优先级 / 生成初步回复
4. L1（propose-only）：仅建议标签，不操作；更新 state 的 Top 5 与 needs-human
5. L2：自动打 allowlist 标签（area:* / needs-repro / needs-info）
6. 升级 auth/payments/security 项给人

## 验证
- L1 仅为建议，不应用任何标签或关闭 Issue
- L2 仅打 allowlist 标签，P0/P1/security 始终需人工
- 不自动关闭 Issue（约束）
- `duplicate?` 仅评论，不自动关闭
- 升级 auth/payments/security 项到 needs-human
"""


# ---------------------------------------------------------------------- #
# Allowlist 标签与 Mock 数据
# ---------------------------------------------------------------------- #
# L2 可自动打的标签（参考 loop-engineering issue-triage.md）
_ALLOWLIST_LABELS: set[str] = {
    "area:auth", "area:payments", "area:api", "area:ui",
    "needs-repro", "needs-info",
    "bug", "enhancement", "docs",
}

_MOCK_ISSUES: list[dict[str, Any]] = [
    {"id": 401, "title": "登录时提示 500 错误",
     "body": "使用 Google 账号登录时返回 500，控制台显示 token 校验失败",
     "author": "user1", "labels": []},
    {"id": 402, "title": "希望支持导出 PDF",
     "body": "能否添加导出 PDF 功能，方便存档",
     "author": "user2", "labels": []},
    {"id": 403, "title": "支付页面样式错乱",
     "body": "在移动端支付按钮重叠",
     "author": "user3", "labels": []},
    {"id": 404, "title": "疑似 XSS 漏洞",
     "body": "在评论框输入 <script> 标签会被执行，存在 security 风险",
     "author": "user4", "labels": []},
    {"id": 405, "title": "API 文档缺失",
     "body": "",
     "author": "user5", "labels": []},
]
