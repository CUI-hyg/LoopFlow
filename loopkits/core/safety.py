"""安全门控统一入口。

整合 :class:`~loopkits.core.constraints.Constraints`（路径/行为门控）、
:class:`~loopkits.core.budget.Budget`（预算降级/杀停）、worktree 隔离与
:class:`~loopkits.core.state.State`（暂停标志）为统一的安全门控层，供
Loop / WorkFlow / CLI 各层调用。

同时提供 :class:`TrustUpgrade` 管理信任级别（L1→L2→L3）的渐进升级路径：
基于历史运行结果（成功/失败计数）判断是否允许升级，避免越权。

设计要点：

- :class:`SafetyGate` 是无状态门面，所有检查委托给传入的 Constraints /
  Budget / State 对象，便于测试与替换。
- :class:`SafetyLevel` 用枚举表达预算状态（OK / DEGRADED / STOPPED）。
- :class:`SafetyError` 在 worktree 隔离等硬性约束被违反时抛出。
- :class:`TrustUpgrade` 维护运行历史，建议升级条件：连续 N 次成功且无失败。
"""

from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path
from typing import Any

from loopkits.core.budget import Budget
from loopkits.core.constraints import Constraints
from loopkits.core.loop import TrustLevel
from loopkits.core.state import State

__all__ = [
    "SafetyLevel",
    "SafetyError",
    "SafetyGate",
    "TrustUpgrade",
]


class SafetyLevel(str, Enum):
    """预算安全级别。"""

    OK = "OK"                # 预算充足，正常运行
    DEGRADED = "DEGRADED"    # 超过降级阈值，应切 L1 仅报告
    STOPPED = "STOPPED"      # 预算耗尽，应停止循环


class SafetyError(Exception):
    """安全门控违例（如无人值守代码变更未在 worktree 中进行）。"""


class SafetyGate:
    """安全门控统一入口：整合 constraints + budget + worktree + pause 检查。

    所有方法均为无状态检查（依赖传入对象），便于在 Loop / WorkFlow / CLI
    各层按需调用而不耦合具体实现。
    """

    def check_path(
        self,
        path: str | Path,
        constraints: Constraints | None = None,
    ) -> bool:
        """检查路径是否允许编辑。

        Args:
            path: 待检查的路径。
            constraints: 约束集合；为 None 则使用默认约束。

        Returns:
            True 表示允许，False 表示禁止（命中黑名单）。
        """
        cs = constraints if constraints is not None else Constraints()
        return cs.check_path(path)

    def check_budget(self, budget: Budget) -> SafetyLevel:
        """检查预算状态，返回安全级别。

        判定优先级：

        1. ``should_stop()`` 为真 → :attr:`SafetyLevel.STOPPED`
        2. ``is_degraded()`` 为真 → :attr:`SafetyLevel.DEGRADED`
        3. 否则 → :attr:`SafetyLevel.OK`
        """
        if budget.should_stop():
            return SafetyLevel.STOPPED
        if budget.is_degraded():
            return SafetyLevel.DEGRADED
        return SafetyLevel.OK

    def require_worktree(
        self,
        path: str | Path,
        is_unattended: bool,
        in_worktree: bool = False,
    ) -> None:
        """强制无人值守代码变更在 worktree 中进行。

        无人值守（``is_unattended=True``）且涉及代码变更的路径不在 worktree
        中时，抛 :class:`SafetyError`。有人值守时直接放行（人工监控）。

        当调用方声明 ``in_worktree=True`` 时，会用 ``git rev-parse
        --is-inside-work-tree`` 真正验证，不盲目信任传入参数，避免绕过。

        Args:
            path: 待变更的路径（用于错误信息）。
            is_unattended: 是否无人值守（L3 全自动）。
            in_worktree: 当前是否已在 worktree 中。

        Raises:
            SafetyError: 无人值守代码变更未在 worktree 中。
        """
        if not is_unattended:
            return
        if not in_worktree:
            raise SafetyError(
                f"无人值守代码变更必须在 worktree 中进行：{path}。"
                "请先通过 `loopflow worktree create` 创建隔离 worktree。"
            )
        # 调用方声明已在 worktree 中：用 git 真正验证，不盲目信任
        if not _is_inside_git_worktree():
            raise SafetyError(
                f"无人值守代码变更必须在 worktree 中进行：{path}。"
                "调用方声明 in_worktree=True，但 git 检测未处于工作树中。"
            )

    def check_pause(self, state: State) -> bool:
        """检查 loop-pause-all 杀停开关是否激活。

        Returns:
            True 表示已暂停（应立即退出），False 表示正常运行。
        """
        return state.is_paused()

    def full_check(
        self,
        path: str | Path | None = None,
        constraints: Constraints | None = None,
        budget: Budget | None = None,
        state: State | None = None,
        is_unattended: bool = False,
        in_worktree: bool = False,
    ) -> SafetyLevel:
        """一次性执行全部安全检查。

        按优先级返回最严重的级别：

        1. 暂停标志激活 → :attr:`SafetyLevel.STOPPED`
        2. worktree 隔离违例 → 抛 :class:`SafetyError`
        3. 预算耗尽 → :attr:`SafetyLevel.STOPPED`
        4. 路径命中黑名单 → 抛 :class:`SafetyError`
        5. 预算降级 → :attr:`SafetyLevel.DEGRADED`
        6. 否则 → :attr:`SafetyLevel.OK`
        """
        if state is not None and self.check_pause(state):
            return SafetyLevel.STOPPED
        if path is not None and is_unattended:
            self.require_worktree(path, is_unattended, in_worktree)
        if budget is not None:
            level = self.check_budget(budget)
            if level == SafetyLevel.STOPPED:
                return SafetyLevel.STOPPED
        if path is not None:
            # constraints 为 None 时使用默认约束，而非跳过路径检查
            cs = constraints if constraints is not None else Constraints()
            if not self.check_path(path, cs):
                raise SafetyError(
                    f"路径 '{path}' 命中约束黑名单，禁止编辑。"
                    f"违规：{cs.violations_list()}"
                )
        if budget is not None and budget.is_degraded():
            return SafetyLevel.DEGRADED
        return SafetyLevel.OK


class TrustUpgrade:
    """信任级别升级路径管理。

    管理信任级别（L1→L2→L3）的渐进升级：基于历史运行结果判断是否允许
    升级。核心原则：**至少 N 次连续成功且无失败才允许升级**，避免越权。

    Args:
        min_success: 允许升级所需的连续成功次数（默认 3）。
    """

    # 升级路径：L1 → L2 → L3
    _UPGRADE_PATH: dict[TrustLevel, TrustLevel] = {
        TrustLevel.L1: TrustLevel.L2,
        TrustLevel.L2: TrustLevel.L3,
    }

    def __init__(self, min_success: int = 3) -> None:
        self.min_success: int = min_success
        # 按级别记录的成功/失败计数
        self._success_counts: dict[TrustLevel, int] = {
            TrustLevel.L1: 0,
            TrustLevel.L2: 0,
            TrustLevel.L3: 0,
        }
        self._failure_counts: dict[TrustLevel, int] = {
            TrustLevel.L1: 0,
            TrustLevel.L2: 0,
            TrustLevel.L3: 0,
        }
        self._current_level: TrustLevel = TrustLevel.L1

    # ------------------------------------------------------------------ #
    # 升级判定
    # ------------------------------------------------------------------ #
    def can_upgrade(
        self,
        current: TrustLevel,
        target: TrustLevel,
    ) -> bool:
        """判断是否允许从 current 升级到 target。

        升级条件：

        1. target 必须是 current 的下一级（L1→L2 或 L2→L3），不可跨级。
        2. current 级别的连续成功次数 >= :attr:`min_success`。
        3. current 级别无失败记录。

        仅使用内部维护的计数，不接受外部传入参数，避免绕过。

        Args:
            current: 当前信任级别。
            target: 目标信任级别。

        Returns:
            True 表示允许升级。
        """
        # 必须是相邻级别
        if self._UPGRADE_PATH.get(current) != target:
            return False
        # 仅使用内部计数，不接受外部参数，避免绕过
        return (
            self._success_counts[current] >= self.min_success
            and self._failure_counts[current] == 0
        )

    def upgrade_path(self, from_level: TrustLevel) -> list[TrustLevel]:
        """返回从 from_level 开始的升级路径列表。

        如 L1 → [L2, L3]；L2 → [L3]；L3 → []。
        """
        path: list[TrustLevel] = []
        level = from_level
        while level in self._UPGRADE_PATH:
            nxt = self._UPGRADE_PATH[level]
            path.append(nxt)
            level = nxt
        return path

    def record_run(self, level: TrustLevel, success: bool) -> None:
        """记录一次运行结果。

        Args:
            level: 运行时的信任级别。
            success: 是否成功。
        """
        if success:
            self._success_counts[level] += 1
        else:
            self._failure_counts[level] += 1
            # 失败时重置当前级别的连续成功计数，要求重新累积
            self._success_counts[level] = 0

    def suggest_level(self) -> TrustLevel:
        """基于历史运行记录建议当前应使用的信任级别。

        如果当前级别已达升级条件，返回升级后的级别；否则返回当前级别。
        """
        current = self._current_level
        path = self._UPGRADE_PATH.get(current)
        if path is not None and self.can_upgrade(current, path):
            return path
        return current

    def set_current_level(self, level: TrustLevel) -> None:
        """设置当前信任级别（升级成功后调用）。"""
        self._current_level = level

    def reset(self, level: TrustLevel = TrustLevel.L1) -> None:
        """重置历史记录与当前级别（通常在降级或重置时调用）。"""
        for lvl in self._success_counts:
            self._success_counts[lvl] = 0
            self._failure_counts[lvl] = 0
        self._current_level = level

    @property
    def current_level(self) -> TrustLevel:
        """当前信任级别。"""
        return self._current_level

    def success_count(self, level: TrustLevel) -> int:
        """返回指定级别的成功次数。"""
        return self._success_counts.get(level, 0)

    def failure_count(self, level: TrustLevel) -> int:
        """返回指定级别的失败次数。"""
        return self._failure_counts.get(level, 0)

    def __repr__(self) -> str:
        return (
            f"<TrustUpgrade current={self._current_level.value} "
            f"min_success={self.min_success}>"
        )


def _is_inside_git_worktree() -> bool:
    """用 ``git rev-parse --is-inside-work-tree`` 真正检测当前是否在 git 工作树中。

    供 :meth:`SafetyGate.require_worktree` 验证调用方声明，避免盲目信任
    传入的 ``in_worktree`` 参数。git 不可用或非仓库时返回 False。
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.SubprocessError, OSError):
        return False
