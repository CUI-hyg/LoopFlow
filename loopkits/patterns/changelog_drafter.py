"""Changelog Drafter 模式 — 变更日志草案。

基于 git log 生成 changelog 草案（RELEASE_NOTES_DRAFT.md）。L1 仅生成草案，
人工批准后方可发布或更新 CHANGELOG。

参考 loop-engineering 的 changelog-drafter 模式：节奏 ``1d`` 或发布准备时触发，
低风险、高价值，是 Post-Merge Cleanup 的优秀伴侣。
"""

from __future__ import annotations

from typing import Any

from loopkits.core.loop import Loop, TrustLevel
from loopkits.core.state import State
from loopkits.core.workflow import Step, WorkFlow
from loopkits.patterns.base import Pattern, PatternMeta

__all__ = ["ChangelogDrafter"]


class ChangelogDrafter(Pattern):
    """变更日志草案模式：扫描 git log → 分类提交 → 生成 RELEASE_NOTES_DRAFT.md。"""

    meta: PatternMeta = PatternMeta(
        name="changelog-drafter",
        description="基于 git log 生成 changelog 草案（RELEASE_NOTES_DRAFT.md）",
        default_level=TrustLevel.L1,
        cadence="1d",
        tags=["changelog", "release-notes", "git", "docs"],
    )

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #
    def _execute(self, state: State) -> dict[str, Any]:
        """执行变更日志草案：扫描提交 → 分类 → 生成草案。"""
        git = self._service("git")
        commits = self._fetch_commits(git)
        categorized = self._categorize_commits(commits)
        draft = self._generate_draft(categorized)

        result: dict[str, Any] = {
            "commits_scanned": len(commits),
            "by_category": categorized["by_category"],
            "breaking_changes": categorized["breaking_changes"],
            "features": categorized["features"],
            "fixes": categorized["fixes"],
            "other": categorized["other"],
            "draft": draft,
            "draft_path": "RELEASE_NOTES_DRAFT.md",
        }
        state.notes = f"扫描 {len(commits)} 个提交，生成草案 {len(categorized['features'])} 特性 / {len(categorized['fixes'])} 修复"
        return result

    # ------------------------------------------------------------------ #
    # 步骤实现
    # ------------------------------------------------------------------ #
    def _fetch_commits(self, git: Any) -> list[dict[str, Any]]:
        """获取自上次发布以来的提交。无 git 服务时返回 mock 数据。"""
        if git is None:
            return _MOCK_COMMITS
        # 真实服务：git.log(since_last_tag=True)
        return list(git.log_since_last_tag() or [])

    def _categorize_commits(
        self, commits: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """按 conventional commits 分类提交。"""
        by_category: dict[str, int] = {
            "feat": 0, "fix": 0, "docs": 0, "refactor": 0,
            "perf": 0, "test": 0, "chore": 0, "breaking": 0, "other": 0,
        }
        features: list[dict[str, Any]] = []
        fixes: list[dict[str, Any]] = []
        breaking_changes: list[dict[str, Any]] = []
        other: list[dict[str, Any]] = []

        for commit in commits:
            message = commit.get("message", "")
            sha = commit.get("sha", commit.get("id", "?"))[:8]
            author = commit.get("author", "unknown")
            category, description, is_breaking = self._parse_commit_message(message)
            by_category[category] = by_category.get(category, 0) + 1
            if is_breaking:
                by_category["breaking"] = by_category.get("breaking", 0) + 1

            entry = {
                "sha": sha,
                "category": category,
                "description": description,
                "author": author,
                "breaking": is_breaking,
            }
            if is_breaking:
                breaking_changes.append(entry)
            if category == "feat":
                features.append(entry)
            elif category == "fix":
                fixes.append(entry)
            elif category not in ("feat", "fix") and not is_breaking:
                other.append(entry)

        return {
            "by_category": by_category,
            "breaking_changes": breaking_changes,
            "features": features,
            "fixes": fixes,
            "other": other,
        }

    def _parse_commit_message(self, message: str) -> tuple[str, str, bool]:
        """解析 conventional commit 消息：type(scope): description。"""
        first_line = message.split("\n")[0].strip()
        is_breaking = "BREAKING CHANGE" in message or "!" in first_line.split(":")[0]
        # 解析 type
        if ":" in first_line:
            type_part, _, desc = first_line.partition(":")
            # 去除 scope 与 !
            type_str = type_part.split("(")[0].rstrip("!").lower().strip()
            description = desc.strip()
            if type_str in ("feat", "fix", "docs", "refactor", "perf", "test", "chore", "build", "ci"):
                return type_str, description, is_breaking
        return "other", first_line, is_breaking

    def _generate_draft(self, categorized: dict[str, Any]) -> str:
        """生成 RELEASE_NOTES_DRAFT.md 内容。"""
        lines = [
            "# Release Notes (Draft)",
            "",
            "> ⚠️ 此文件由 LoopKits ChangelogDrafter 自动生成，需人工审核后方可发布。",
            "",
        ]
        if categorized["breaking_changes"]:
            lines.append("## ⚠️ Breaking Changes")
            lines.append("")
            for c in categorized["breaking_changes"]:
                lines.append(f"- **{c['sha']}** {c['description']} (@{c['author']})")
            lines.append("")

        if categorized["features"]:
            lines.append("## ✨ Features")
            lines.append("")
            for c in categorized["features"]:
                lines.append(f"- {c['description']} (`{c['sha']}`)")
            lines.append("")

        if categorized["fixes"]:
            lines.append("## 🐛 Bug Fixes")
            lines.append("")
            for c in categorized["fixes"]:
                lines.append(f"- {c['description']} (`{c['sha']}`)")
            lines.append("")

        if categorized["other"]:
            lines.append("## 📦 Other Changes")
            lines.append("")
            for c in categorized["other"]:
                lines.append(f"- [{c['category']}] {c['description']} (`{c['sha']}`)")
            lines.append("")

        lines.append("---")
        lines.append(f"提交分类统计：{categorized['by_category']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Pattern 接口实现
    # ------------------------------------------------------------------ #
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """构建变更日志草案 Loop（单趟生成，L1 仅草案）。"""
        overrides = dict(config_overrides or {})
        overrides.setdefault("max_iterations", 1)
        overrides.setdefault("stop_condition", "RELEASE_NOTES_DRAFT.md 已生成")
        return self._make_loop(overrides)

    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建变更日志草案 WorkFlow：扫描提交 → 分类 → 生成草案。"""
        fetch = Step(
            name="fetch-commits",
            action=lambda ctx: self._fetch_commits(self._service("git")),
            outputs="commits",
        )
        categorize = Step(
            name="categorize-commits",
            action=lambda ctx: self._categorize_commits(ctx.get("commits", [])),
            outputs="categorized",
        )
        generate = Step(
            name="generate-draft",
            action=lambda ctx: self._generate_draft(ctx.get("categorized", {})),
            outputs="draft",
        )
        return WorkFlow(name="changelog-drafter", steps=[fetch, categorize, generate])

    def to_skill_md(self) -> str:
        return """# Skill: changelog-drafter

## 触发条件
- 节奏：每日或发布准备时（tag 触发）
- 触发：`/loop 1d $changelog-scan + $draft-release-notes`

## 步骤
1. 获取自上次发布 tag 以来的 git 提交（通过 git service）
2. 按 conventional commits 分类：feat / fix / docs / refactor / perf / breaking
3. 生成 RELEASE_NOTES_DRAFT.md（Breaking Changes / Features / Bug Fixes / Other）
4. 更新 changelog-drafter-state.md
5. 人工审核后方可发布或更新 CHANGELOG

## 验证
- 仅生成草案，不自动发布或打 tag
- Breaking Changes 必须醒目标注
- 提交分类统计准确
- 草案顶部标注「需人工审核」
- 不修改正式 CHANGELOG.md（除非人工批准）
"""


# ---------------------------------------------------------------------- #
# Mock 数据
# ---------------------------------------------------------------------- #
_MOCK_COMMITS: list[dict[str, Any]] = [
    {"sha": "abc123def", "author": "alice",
     "message": "feat(auth): 支持 OAuth2 登录\n\n新增 Google/GitHub OAuth2 provider"},
    {"sha": "def456abc", "author": "bob",
     "message": "fix(api): 修复分页参数 off-by-one 错误"},
    {"sha": "ghi789jkl", "author": "carol",
     "message": "feat!: 重构用户模型，移除 deprecated 字段\n\nBREAKING CHANGE: User.profile 字段已移除，使用 User.metadata"},
    {"sha": "jkl012mno", "author": "dave",
     "message": "docs: 更新 API 文档"},
    {"sha": "mno345pqr", "author": "eve",
     "message": "fix(upload): 修复大文件上传超时"},
    {"sha": "pqr678stu", "author": "frank",
     "message": "refactor(db): 简化连接池配置"},
    {"sha": "stu901vwx", "author": "grace",
     "message": "perf(cache): 优化缓存命中率"},
    {"sha": "vwx234yza", "author": "heidi",
     "message": "chore: 升级开发依赖"},
]
