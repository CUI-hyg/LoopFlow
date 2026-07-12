"""约束解析与安全门控。

Constraints 是 Loop 的「安全护栏」：从 ``loop-constraints.md``（人可读
Markdown）解析出可编程约束，在每次执行前检查路径与行为是否被允许。参考
loop-engineering 的 loop-constraints 模板与 safety.md 路径黑名单。

默认约束（即使无配置文件也生效）：

- 路径保护：禁止编辑 ``.env`` / ``secrets/`` / ``credentials/`` / 基础设施配置等
- 合并：未经批准不自动合并 main
- 沟通：未经批准不关闭 Issue / PR
- 代码：不禁用测试、单次最多 3 次修复尝试
- 预算：80% 日上限切仅报告、loop-pause-all 立即退出
"""

from __future__ import annotations

import fnmatch
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

__all__ = ["Constraint", "ConstraintType", "Constraints"]


class ConstraintType(str, Enum):
    """约束类型。"""

    PATH = "path"              # 路径保护
    CODE = "code"              # 代码行为
    COMMUNICATION = "communication"  # 沟通行为
    BUDGET = "budget"          # 预算规则
    MERGE = "merge"            # 合并策略


class Constraint(BaseModel):
    """单条约束。

    Attributes:
        type: 约束类型。
        rule: 人可读的规则描述（如 "Never edit .env files"）。
        value: 机器可读的匹配值（路径 glob 模式或行为关键字）。
    """

    type: ConstraintType
    rule: str
    value: str = ""


# 默认路径黑名单（参考 loop-engineering safety.md）
_DEFAULT_PATH_DENYLIST: list[str] = [
    ".env",
    ".env.*",
    "**/secrets/**",
    "**/credentials/**",
    "**/*_key*",
    "**/*_secret*",
    ".terraform/**",
    "k8s/production/**",
    "**/migrations/**",
    "auth/**",
    "payments/**",
    "billing/**",
    "loop-budget.yaml",
    "loop-constraints.md",
]

# 默认行为约束
_DEFAULT_CONSTRAINTS: list[Constraint] = [
    Constraint(type=ConstraintType.MERGE, rule="Never auto-merge to main without human approval", value="auto-merge-main"),
    Constraint(type=ConstraintType.COMMUNICATION, rule="Never close an issue or PR without approval", value="close-issue"),
    Constraint(type=ConstraintType.CODE, rule="Never disable tests to make CI green", value="disable-tests"),
    Constraint(type=ConstraintType.CODE, rule="Max 3 fix attempts per item; escalate after", value="max-attempts:3"),
    Constraint(type=ConstraintType.BUDGET, rule="If token spend hits 80% of daily cap, switch to report-only", value="degrade-at:0.8"),
    Constraint(type=ConstraintType.BUDGET, rule="If loop-pause-all is active, exit immediately", value="pause-all"),
]


class Constraints(BaseModel):
    """约束集合：解析 loop-constraints.md 并提供路径/行为检查。

    Attributes:
        constraints: 已解析的约束列表。
        path_denylist: 路径黑名单 glob 模式列表。
        path_allowlist: 路径白名单（显式允许，覆盖黑名单）。
        violations: 最近一次检查中发现的违规记录。
    """

    constraints: list[Constraint] = Field(default_factory=list)
    path_denylist: list[str] = Field(default_factory=lambda: list(_DEFAULT_PATH_DENYLIST))
    path_allowlist: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)

    def __init__(self, **data):
        super().__init__(**data)
        # 确保默认约束始终存在
        existing_values = {c.value for c in self.constraints}
        for default in _DEFAULT_CONSTRAINTS:
            if default.value not in existing_values:
                self.constraints.append(default)

    # ------------------------------------------------------------------ #
    # 加载
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: str | Path = "loop-constraints.md") -> "Constraints":
        """从 loop-constraints.md 解析约束；文件不存在则仅用默认约束。"""
        p = Path(path)
        if not p.exists():
            return cls()
        return cls.from_markdown(p.read_text(encoding="utf-8"))

    @classmethod
    def from_markdown(cls, text: str) -> "Constraints":
        """从 Markdown 文本解析约束（按 ## 段落归类）。"""
        instance = cls()
        current_section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                current_section = stripped[3:].strip().lower()
                continue
            if not stripped or stripped.startswith("<!--") or stripped.startswith(">"):
                continue
            # 以 "- " 开头的列表项视为规则
            if stripped.startswith("- "):
                rule_text = stripped[2:].strip()
                ctype = _section_to_type(current_section)
                value = _extract_value(rule_text)
                instance.constraints.append(
                    Constraint(type=ctype, rule=rule_text, value=value)
                )
                # 路径段中的规则同步加入黑名单（提取路径模式）
                if ctype == ConstraintType.PATH:
                    patterns = _extract_paths(rule_text)
                    instance.path_denylist.extend(patterns)
        return instance

    # ------------------------------------------------------------------ #
    # 检查
    # ------------------------------------------------------------------ #
    def check_path(self, path: str | Path) -> bool:
        """检查路径是否允许编辑。允许返回 True，禁止返回 False 并记录违规。"""
        self.violations.clear()
        target = str(path).replace("\\", "/")
        # 白名单优先
        for pattern in self.path_allowlist:
            if fnmatch.fnmatch(target, pattern) or fnmatch.fnmatch(target, f"**/{pattern}"):
                return True
        # 黑名单匹配
        for pattern in self.path_denylist:
            if _match_path(target, pattern):
                self.violations.append(f"路径 '{target}' 命中黑名单规则 '{pattern}'")
                return False
        return True

    def check_action(self, action: str) -> bool:
        """检查行为是否允许。允许返回 True，禁止返回 False 并记录违规。

        ``action`` 为行为关键字，如 ``auto-merge-main`` / ``close-issue`` /
        ``disable-tests`` 等。
        """
        self.violations.clear()
        action_lower = action.lower().strip()
        for c in self.constraints:
            if c.type in (ConstraintType.MERGE, ConstraintType.COMMUNICATION, ConstraintType.CODE):
                if c.value and c.value.lower() == action_lower:
                    self.violations.append(f"行为 '{action}' 被约束禁止：{c.rule}")
                    return False
        return True

    def violations_list(self) -> list[str]:
        """返回最近一次检查的违规列表。"""
        return list(self.violations)

    def add_path_deny(self, pattern: str) -> None:
        """新增路径黑名单模式。"""
        if pattern not in self.path_denylist:
            self.path_denylist.append(pattern)

    def add_path_allow(self, pattern: str) -> None:
        """新增路径白名单模式（覆盖黑名单）。"""
        if pattern not in self.path_allowlist:
            self.path_allowlist.append(pattern)


# ---------------------------------------------------------------------- #
# 辅助函数
# ---------------------------------------------------------------------- #
def _section_to_type(section: str) -> ConstraintType:
    """将 Markdown 段落标题映射到约束类型。"""
    section = section.lower()
    if "path" in section:
        return ConstraintType.PATH
    if "merge" in section or "push" in section:
        return ConstraintType.MERGE
    if "code" in section:
        return ConstraintType.CODE
    if "communication" in section or "issue" in section:
        return ConstraintType.COMMUNICATION
    if "budget" in section:
        return ConstraintType.BUDGET
    return ConstraintType.CODE


def _extract_value(rule: str) -> str:
    """从规则文本提取机器可读的关键字。"""
    lower = rule.lower()
    if "auto-merge" in lower and "main" in lower:
        return "auto-merge-main"
    if "close" in lower and ("issue" in lower or "pr" in lower):
        return "close-issue"
    if "disable" in lower and "test" in lower:
        return "disable-tests"
    if "pause-all" in lower or "loop-pause-all" in lower:
        return "pause-all"
    if "80%" in lower or "report-only" in lower:
        return "degrade-at:0.8"
    if "max" in lower and "attempt" in lower:
        return "max-attempts:3"
    return rule[:40]


def _extract_paths(rule: str) -> list[str]:
    """从规则文本中提取路径模式（反引号包裹或 .env/xxx/ 形式）。"""
    import re

    patterns: list[str] = []
    # 反引号包裹的路径
    for match in re.findall(r"`([^`]+)`", rule):
        if "/" in match or match.startswith("."):
            patterns.append(match)
    return patterns


def _match_path(target: str, pattern: str) -> bool:
    """路径匹配：段级匹配，确保子目录中的敏感文件也被拦截。

    所有 pattern 统一按段级匹配：去除 ``**/`` 前缀与 ``/**`` 后缀后，
    在 target 的任意层级查找匹配的段或段序列。这样 ``.env`` 既能匹配
    根目录的 ``.env``，也能匹配 ``config/.env``，避免子目录绕过。
    """
    # 标准化：用字符串前缀剥离（非字符级 lstrip），避免 "./.env"→"env"
    target = _normalize_relpath(target)
    pattern = _normalize_relpath(pattern)
    if not target or not pattern:
        return False
    target_parts = [p for p in target.split("/") if p]
    # 去除 **/ 前缀（统一按任意层级匹配）
    if pattern.startswith("**/"):
        pattern = pattern[3:]
    # 去除 /** 后缀（目录递归 → 按目录段匹配）
    if pattern.endswith("/**"):
        pattern = pattern[:-3]
    # 去除末尾单独的 / （目录本身）
    if pattern.endswith("/"):
        pattern = pattern[:-1]
    if not pattern:
        return True
    core_parts = [p for p in pattern.split("/") if p]
    if not core_parts:
        return True
    if len(core_parts) == 1:
        # 单段：任意 target 段匹配（fnmatch 支持通配，如 .env / .env.* / *_key*）
        seg = core_parts[0]
        for part in target_parts:
            if part == seg or fnmatch.fnmatch(part, seg):
                return True
        return False
    # 多段：target 中存在与 core_parts 连续匹配的段序列（如 k8s/production）
    return _contains_segment_sequence(target_parts, core_parts)


def _normalize_relpath(s: str) -> str:
    """标准化相对路径：统一反斜杠，去除前导 ``./``（字符串级，非字符级）。"""
    s = s.replace("\\", "/")
    # 循环去除前导 ./ （避免 lstrip("./") 把 "./.env" 误剥成 "env"）
    while s.startswith("./"):
        s = s[2:]
    return s


def _contains_segment_sequence(target_parts: list[str], core_parts: list[str]) -> bool:
    """target 中是否包含与 core_parts 连续匹配的段序列（支持 fnmatch 通配）。"""
    n, m = len(target_parts), len(core_parts)
    if m > n or m == 0:
        return False
    for i in range(n - m + 1):
        if all(fnmatch.fnmatch(target_parts[i + j], core_parts[j]) for j in range(m)):
            return True
    return False
