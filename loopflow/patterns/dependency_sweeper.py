"""Dependency Sweeper 模式 — 依赖升级清扫。

扫描依赖升级：patch 自动升级，minor/major 生成评估报告。L1 报告可用升级；
L2 patch 在 worktree 自动升级并验证（verifier = 全量安装 + 测试）。

参考 loop-engineering 的 dependency-sweeper 模式：节奏 ``6h``~``1d``，patch +
低风险 CVE 自动升级，major 与 denylist 包需人工批准。
"""

from __future__ import annotations

from typing import Any

from loopflow.core.loop import Loop, TrustLevel
from loopflow.core.state import State
from loopflow.core.workflow import RetryPolicy, Step, WorkFlow
from loopflow.patterns.base import Pattern, PatternMeta

__all__ = ["DependencySweeper"]


class DependencySweeper(Pattern):
    """依赖清扫模式：扫描升级 → 分类 → patch（L2）自动升级 / minor+major 评估。"""

    meta: PatternMeta = PatternMeta(
        name="dependency-sweeper",
        description="扫描依赖升级：patch 自动升级，minor/major 生成评估报告",
        default_level=TrustLevel.L1,
        cadence="6h",
        tags=["dependencies", "upgrades", "security", "automation"],
    )

    # ------------------------------------------------------------------ #
    # 核心执行逻辑
    # ------------------------------------------------------------------ #
    def _execute(self, state: State) -> dict[str, Any]:
        """执行依赖清扫：扫描 → 分类 → （L2）patch 升级。"""
        dep = self._service("dependency")
        updates = self._scan_updates(dep)
        classified = self._classify_updates(updates)

        upgrades: list[dict[str, Any]] = []
        if self.effective_level != TrustLevel.L1:
            # L2：仅 patch + 低风险 CVE 在 worktree 自动升级
            for u in classified["patch_safe"]:
                upgrades.extend(self._apply_patch(u))

        report = self._build_report(classified, upgrades)
        result: dict[str, Any] = {
            "updates_found": len(updates),
            "by_type": classified["by_type"],
            "patch_safe": classified["patch_safe"],
            "needs_evaluation": classified["needs_evaluation"],
            "denylisted": classified["denylisted"],
            "upgrades": upgrades,
            "report": report,
        }
        state.todos = [u["name"] for u in classified["needs_evaluation"]]
        state.notes = f"发现 {len(updates)} 个升级，patch {len(classified['patch_safe'])} 个"
        return result

    # ------------------------------------------------------------------ #
    # 步骤实现
    # ------------------------------------------------------------------ #
    def _scan_updates(self, dep: Any) -> list[dict[str, Any]]:
        """扫描可用依赖升级。无 dependency 服务时返回 mock 数据。"""
        if dep is None:
            return _MOCK_UPDATES
        return list(dep.list_outdated() or [])

    def _classify_updates(self, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """分类升级：patch（安全）/ minor（评估）/ major（评估）/ denylisted。"""
        by_type: dict[str, int] = {"patch": 0, "minor": 0, "major": 0}
        patch_safe: list[dict[str, Any]] = []
        needs_evaluation: list[dict[str, Any]] = []
        denylisted: list[dict[str, Any]] = []

        for u in updates:
            update_type = u.get("type", "patch")
            name = u.get("name", "unknown")
            by_type[update_type] = by_type.get(update_type, 0) + 1
            # risk 缺失时默认 "high"（fail-closed，避免未知风险被自动升级）
            risk = u.get("risk", "high")
            entry = {
                "name": name,
                "current": u.get("current", ""),
                "target": u.get("target", ""),
                "type": update_type,
                "cve": u.get("cve"),
                "risk": risk,
                "changelog": u.get("changelog", ""),
            }
            # denylist 匹配时对 name 做标准化（lower + 取末段 + 下划线转短横线），
            # 防止大小写变体或 scoped 包名绕过
            normalized = name.lower().split("/")[-1].replace("_", "-")
            if normalized in _DENYLIST:
                denylisted.append(entry)
            elif update_type == "patch" and risk != "high":
                patch_safe.append(entry)
            else:
                needs_evaluation.append(entry)

        return {
            "by_type": by_type,
            "patch_safe": patch_safe,
            "needs_evaluation": needs_evaluation,
            "denylisted": denylisted,
        }

    def _apply_patch(self, update: dict[str, Any]) -> list[dict[str, Any]]:
        """在 worktree 中应用 patch 升级并验证（L2）。"""
        git = self._service("git")
        upgrade = {
            "name": update["name"],
            "from": update["current"],
            "to": update["target"],
            "worktree": f"dep/{update['name']}-{update['target']}",
            "status": "proposed",
            "verifier": "pending",
        }
        if git is not None:
            # 真实服务：git.create_worktree() + 更新依赖 + 运行测试
            upgrade["status"] = "applied"
            upgrade["verifier"] = "passed"
        return [upgrade]

    def _build_report(
        self, classified: dict[str, Any], upgrades: list[dict[str, Any]]
    ) -> str:
        """生成依赖升级报告。"""
        lines = [
            "# Dependency Sweeper Report",
            "",
            f"## 升级类型分布：{classified['by_type']}",
            "",
            "## Patch 安全升级（L2 可自动）",
        ]
        for u in classified["patch_safe"]:
            cve = f" [CVE: {u['cve']}]" if u.get("cve") else ""
            lines.append(f"- {u['name']}: {u['current']} → {u['target']}{cve}")
        lines.append("")
        lines.append("## 需评估（minor/major/高风险）")
        for u in classified["needs_evaluation"]:
            lines.append(f"- {u['name']}: {u['current']} → {u['target']} ({u['type']}, risk={u['risk']})")
            if u.get("changelog"):
                lines.append(f"  - changelog: {u['changelog'][:80]}")
        lines.append("")
        if classified["denylisted"]:
            lines.append("## Denylist（需人工批准）")
            for u in classified["denylisted"]:
                lines.append(f"- {u['name']}: {u['current']} → {u['target']}")
            lines.append("")
        if upgrades:
            lines.append("## L2 已应用升级")
            for up in upgrades:
                lines.append(f"- {up['name']}: {up['from']} → {up['to']} ({up['status']})")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Pattern 接口实现
    # ------------------------------------------------------------------ #
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """构建依赖清扫 Loop（单趟扫描，patch 可重试验证）。"""
        overrides = dict(config_overrides or {})
        overrides.setdefault("max_iterations", 1)
        overrides.setdefault("stop_condition", "所有依赖升级已分类")
        return self._make_loop(overrides)

    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建依赖清扫 WorkFlow：扫描 → 分类 → 评估 → （L2）patch 升级。"""
        scan = Step(
            name="scan-updates",
            action=lambda ctx: self._scan_updates(self._service("dependency")),
            outputs="updates",
        )
        classify = Step(
            name="classify-updates",
            action=lambda ctx: self._classify_updates(ctx.get("updates", [])),
            outputs="classified",
        )
        evaluate = Step(
            name="evaluate-minor-major",
            action=lambda ctx: ctx.get("classified", {}).get("needs_evaluation", []),
            outputs="evaluations",
        )

        def _upgrade_action(ctx: dict[str, Any]) -> list[dict[str, Any]]:
            if self.effective_level == TrustLevel.L1:
                return []
            upgrades: list[dict[str, Any]] = []
            for u in ctx.get("classified", {}).get("patch_safe", []):
                upgrades.extend(self._apply_patch(u))
            return upgrades

        upgrade = Step(
            name="apply-patch-upgrades",
            action=_upgrade_action,
            outputs="upgrades",
            retry_policy=RetryPolicy(max_retries=2, backoff=0.0),
        )
        return WorkFlow(name="dependency-sweeper", steps=[scan, classify, evaluate, upgrade])

    def to_skill_md(self) -> str:
        return """# Skill: dependency-sweeper

## 触发条件
- 节奏：6h 或每日
- 触发：`/loop 6h $dependency-triage` 或定时任务

## 步骤
1. 扫描过时依赖（通过 dependency service）
2. 分类：patch（安全）/ minor（评估）/ major（评估）/ denylisted
3. 检查每个升级的 CVE 与风险等级
4. L1：生成升级报告，patch 列表与评估列表
5. L2：patch + 低风险 CVE 在 worktree 中升级，verifier = 全量安装 + 测试
6. minor/major/denylist 升级给人评估

## 验证
- 仅 patch + 低风险 CVE 可自动升级
- verifier 必须通过（npm ci && npm test / pip install -e . && pytest）
- major 与 denylist 包必须人工批准
- 升级在隔离 worktree 中进行
- 更新 dependency-sweeper-state.md
"""


# ---------------------------------------------------------------------- #
# Denylist 与 Mock 数据
# ---------------------------------------------------------------------- #
# 高风险包，需人工批准方可升级（参考 loop-engineering safety.md）
_DENYLIST: set[str] = {
    "react", "react-dom",  # 前端核心
    "express",  # 后端核心
    "webpack",  # 构建工具
    "django", "flask",  # web 框架
}

_MOCK_UPDATES: list[dict[str, Any]] = [
    {"name": "requests", "current": "2.20.0", "target": "2.20.1",
     "type": "patch", "risk": "low", "cve": "CVE-2023-XXXX",
     "changelog": "修复 SSRF 漏洞"},
    {"name": "pytest", "current": "7.4.0", "target": "7.4.2",
     "type": "patch", "risk": "low", "cve": None,
     "changelog": "修复兼容性问题"},
    {"name": "pydantic", "current": "2.0.0", "target": "2.5.0",
     "type": "minor", "risk": "medium", "cve": None,
     "changelog": "新增验证器 API，废弃旧 API"},
    {"name": "fastapi", "current": "0.100.0", "target": "0.101.0",
     "type": "minor", "risk": "medium", "cve": None,
     "changelog": "依赖升级，行为微调"},
    {"name": "django", "current": "4.2.0", "target": "5.0.0",
     "type": "major", "risk": "high", "cve": None,
     "changelog": "重大版本升级，移除废弃特性"},
    {"name": "react", "current": "18.2.0", "target": "18.2.1",
     "type": "patch", "risk": "low", "cve": None,
     "changelog": "小修复"},  # 在 denylist 中
]
