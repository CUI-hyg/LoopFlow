"""Post-Merge Cleanup 模式 — 合并后清理。

合并后清理分支、更新 Issue 状态、标记关闭。L1 报告待清理项；L2 执行清理
（需人确认）。不触碰 denylist 路径。

参考 loop-engineering 的 post-merge-cleanup 模式：节奏 ``1d``，仅小清理，
大债务开 ticket，denylist 路径需人工批准。
"""

from __future__ import annotations

from typing import Any

from loopkits.core.loop import Loop, TrustLevel
from loopkits.core.state import State
from loopkits.core.workflow import Step, WorkFlow
from loopkits.patterns.base import Pattern, PatternMeta

__all__ = ["PostMergeCleanup"]


class PostMergeCleanup(Pattern):
    """合并后清理模式：扫描已合并 PR → 清理分支 → 更新 Issue → 标记关闭。"""

    meta: PatternMeta = PatternMeta(
        name="post-merge-cleanup",
        description="合并后清理分支、更新 Issue 状态、标记关闭",
        default_level=TrustLevel.L1,
        cadence="1d",
        tags=["cleanup", "branches", "issues", "merge"],
    )

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #
    def _execute(self, state: State) -> dict[str, Any]:
        """执行合并后清理：扫描已合并 PR → 生成清理清单 → （L2）执行。"""
        github = self._service("github")
        git = self._service("git")
        merged_prs = self._fetch_merged_prs(github)
        cleanup_items = self._build_cleanup_list(merged_prs, github)

        executed: list[dict[str, Any]] = []
        if self.effective_level != TrustLevel.L1:
            executed = self._execute_cleanup(cleanup_items, git, github)

        report = self._build_report(cleanup_items, executed)
        result: dict[str, Any] = {
            "merged_prs_scanned": len(merged_prs),
            "cleanup_items": cleanup_items,
            "executed": executed,
            "pending": [c for c in cleanup_items if c not in executed],
            "report": report,
        }
        state.todos = [c["description"] for c in cleanup_items if c["needs_confirmation"]]
        state.notes = f"扫描 {len(merged_prs)} 个已合并 PR，清理项 {len(cleanup_items)} 个"
        return result

    # ------------------------------------------------------------------ #
    # 步骤实现
    # ------------------------------------------------------------------ #
    def _fetch_merged_prs(self, github: Any) -> list[dict[str, Any]]:
        """获取最近已合并的 PR。无 github 服务时返回 mock 数据。"""
        if github is None:
            return _MOCK_MERGED_PRS
        return list(github.list_pulls(state="closed", merged=True) or [])

    def _build_cleanup_list(
        self, merged_prs: list[dict[str, Any]], github: Any
    ) -> list[dict[str, Any]]:
        """构建清理清单：分支删除 / Issue 关闭 / Issue 标签更新。"""
        items: list[dict[str, Any]] = []
        for pr in merged_prs:
            pr_id = pr.get("id", pr.get("number", "?"))
            branch = pr.get("head_ref", pr.get("branch", f"pr-{pr_id}"))
            # 分支清理
            items.append({
                "type": "delete-branch",
                "pr_id": pr_id,
                "target": branch,
                "description": f"删除已合并分支 {branch}（PR #{pr_id}）",
                "needs_confirmation": False,
                "safe": True,
            })
            # 关联 Issue 关闭
            linked_issues = pr.get("linked_issues", [])
            for issue_num in linked_issues:
                items.append({
                    "type": "close-issue",
                    "pr_id": pr_id,
                    "target": f"issue #{issue_num}",
                    "description": f"关闭 Issue #{issue_num}（PR #{pr_id} 已合并）",
                    "needs_confirmation": True,  # 关闭 Issue 需人工确认
                    "safe": False,
                })
            # Issue 标签更新
            closing_keywords = pr.get("closing_keywords", [])
            for issue_num in closing_keywords:
                items.append({
                    "type": "label-issue",
                    "pr_id": pr_id,
                    "target": f"issue #{issue_num}",
                    "description": f"为 Issue #{issue_num} 添加 'fixed' 标签",
                    "needs_confirmation": False,
                    "safe": True,
                })

        # 查询可清理的陈旧分支（无关联 PR）
        if github is not None:
            stale_branches = list(github.list_stale_branches(days=30) or [])
            for branch in stale_branches:
                items.append({
                    "type": "delete-stale-branch",
                    "pr_id": None,
                    "target": branch,
                    "description": f"删除陈旧分支 {branch}（>30 天无活动）",
                    "needs_confirmation": True,
                    "safe": False,
                })
        return items

    def _execute_cleanup(
        self,
        items: list[dict[str, Any]],
        git: Any,
        github: Any,
    ) -> list[dict[str, Any]]:
        """执行清理（L2，需人确认的项跳过）。"""
        executed: list[dict[str, Any]] = []
        for item in items:
            # 需人确认的项不自动执行
            if item["needs_confirmation"]:
                continue
            result = {
                **item,
                "status": "pending",
            }
            if item["type"] in ("delete-branch", "delete-stale-branch"):
                if git is not None:
                    result["status"] = "done"
                else:
                    result["status"] = "skipped-no-git"
            elif item["type"] == "label-issue":
                if github is not None:
                    result["status"] = "done"
                else:
                    result["status"] = "skipped-no-github"
            else:
                result["status"] = "skipped"
            executed.append(result)
        return executed

    def _build_report(
        self,
        cleanup_items: list[dict[str, Any]],
        executed: list[dict[str, Any]],
    ) -> str:
        """生成清理报告。"""
        lines = ["# Post-Merge Cleanup Report", ""]
        lines.append(f"## 清理项总数：{len(cleanup_items)}")
        lines.append("")
        lines.append("## 可自动执行")
        for c in cleanup_items:
            if not c["needs_confirmation"]:
                lines.append(f"- [{c['type']}] {c['description']}")
        lines.append("")
        lines.append("## 需人确认")
        for c in cleanup_items:
            if c["needs_confirmation"]:
                lines.append(f"- [{c['type']}] {c['description']}")
        lines.append("")
        if executed:
            lines.append("## L2 已执行")
            for e in executed:
                lines.append(f"- {e['description']}: {e['status']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Pattern 接口实现
    # ------------------------------------------------------------------ #
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """构建合并后清理 Loop（单趟扫描，L2 执行安全项）。"""
        overrides = dict(config_overrides or {})
        overrides.setdefault("max_iterations", 1)
        overrides.setdefault("stop_condition", "所有清理项已处理或升级")
        return self._make_loop(overrides)

    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建合并后清理 WorkFlow：扫描已合并 PR → 构建清单 → （L2）执行。"""
        fetch = Step(
            name="fetch-merged-prs",
            action=lambda ctx: self._fetch_merged_prs(self._service("github")),
            outputs="merged_prs",
        )
        build_list = Step(
            name="build-cleanup-list",
            action=lambda ctx: self._build_cleanup_list(
                ctx.get("merged_prs", []), self._service("github")
            ),
            outputs="cleanup_items",
        )

        def _execute_action(ctx: dict[str, Any]) -> list[dict[str, Any]]:
            if self.effective_level == TrustLevel.L1:
                return []
            return self._execute_cleanup(
                ctx.get("cleanup_items", []),
                self._service("git"),
                self._service("github"),
            )

        execute = Step(
            name="execute-cleanup",
            action=_execute_action,
            outputs="executed",
        )
        return WorkFlow(name="post-merge-cleanup", steps=[fetch, build_list, execute])

    def to_skill_md(self) -> str:
        return """# Skill: post-merge-cleanup

## 触发条件
- 节奏：每日或合并后事件
- 触发：`/loop 1d $post-merge-scan`

## 步骤
1. 获取最近已合并的 PR（通过 github service）
2. 构建清理清单：分支删除 / Issue 关闭 / Issue 标签更新
3. 查询陈旧分支（>30 天无活动）
4. L1：生成清理清单报告，更新 post-merge-state.md
5. L2：执行安全项（分支删除、标签更新），需人确认项（Issue 关闭）仅报告

## 验证
- 仅执行 safe=True 的项，需人确认项不自动执行
- 关闭 Issue 必须人工确认（约束：不自动关闭 Issue）
- 不触碰 denylist 路径
- 大债务开 ticket，不自动修复
- 删除分支前确认已合并
"""


# ---------------------------------------------------------------------- #
# Mock 数据
# ---------------------------------------------------------------------- #
_MOCK_MERGED_PRS: list[dict[str, Any]] = [
    {"id": 301, "title": "feat: 添加用户头像上传",
     "head_ref": "feature/avatar", "linked_issues": [201],
     "closing_keywords": [201]},
    {"id": 302, "title": "fix: 修复 token 校验逻辑",
     "head_ref": "fix/token-validation", "linked_issues": [],
     "closing_keywords": [185]},
    {"id": 303, "title": "docs: 更新 README",
     "head_ref": "docs/readme-update", "linked_issues": [],
     "closing_keywords": []},
]
