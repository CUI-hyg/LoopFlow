"""Loop 原语：自治循环。

Loop 是 LoopFlow 公式的核心：**目标 → 执行 → 检查 → 改进 → 重复/停止**。
参考 autoresearch 的 NEVER STOP 自治循环与 loop-engineering 的 L1/L2/L3
信任分级。

核心机制：

- :meth:`run` 迭代执行，每次迭代调用 :meth:`execute_step` →
  :meth:`check_result` → :meth:`decide_continue`。
- 停止条件：达到目标、最大迭代数、预算耗尽、``loop-pause-all`` 暂停标志。
- 信任分级：L1 仅报告、L2 辅助修复（人工监控）、L3 全自动无人值守。
- 执行体可注入：``execute_fn`` 可以是普通函数、Agent 或 :class:`~loopkits.core.workflow.WorkFlow`。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from loopkits.core.budget import Budget
from loopkits.core.memory import Memory
from loopkits.core.state import State

__all__ = ["TrustLevel", "LoopConfig", "LoopResult", "Loop"]


class TrustLevel(str, Enum):
    """信任级别（渐进信任）。"""

    L1 = "L1"  # 仅报告：不修改任何东西，只输出分析
    L2 = "L2"  # 辅助修复：人工监控下进行修复
    L3 = "L3"  # 全自动：无人值守，需严格约束与验证器


class LoopConfig(BaseModel):
    """循环配置。

    Attributes:
        goal: 循环目标描述。
        max_iterations: 最大迭代次数。
        stop_condition: 停止条件描述（人可读，供 Verifier 判断）。
        level: 信任级别，默认 L1（仅报告）。
    """

    goal: str = ""
    max_iterations: int = 10
    stop_condition: str | None = None
    level: TrustLevel = TrustLevel.L1


class LoopResult(BaseModel):
    """循环执行结果。

    Attributes:
        iterations: 实际执行的迭代次数。
        success: 是否达成目标（stop_condition 满足）。
        final_state: 最终状态快照。
        history: 每次迭代的记录列表。
        stop_reason: 停止原因。
    """

    iterations: int = 0
    success: bool = False
    final_state: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)
    stop_reason: str = ""


class Loop:
    """自治循环：目标 → 执行 → 检查 → 改进 → 重复/停止。

    Args:
        config: 循环配置。
        state: 跨迭代状态（持久化）；为 None 则新建空状态。
        memory: 跨迭代记忆（ratchet）；为 None 则新建空记忆。
        budget: Token 预算；为 None 则新建默认预算。
        execute_fn: 执行函数，签名为 ``fn(state) -> result``；可为
            :class:`~loopkits.core.workflow.WorkFlow`（可调用）或 Agent。
        check_fn: 检查函数，签名为 ``fn(state, result) -> bool``，返回是否
            达成目标。为 None 则使用默认检查（结果为真值即视为达成）。
        decide_fn: 决策函数，签名为 ``fn(state) -> bool``，返回是否继续。
            为 None 则使用默认决策（综合 max_iterations / budget / pause）。
    """

    def __init__(
        self,
        config: LoopConfig,
        state: State | None = None,
        memory: Memory | None = None,
        budget: Budget | None = None,
        execute_fn: Callable[[State], Any] | None = None,
        check_fn: Callable[[State, Any], bool] | None = None,
        decide_fn: Callable[[State], bool] | None = None,
    ):
        self.config = config
        self.state = state or State(goal=config.goal)
        self.memory = memory or Memory()
        self.budget = budget or Budget()
        self._execute_fn = execute_fn
        self._check_fn = check_fn
        self._decide_fn = decide_fn
        # 若 state.goal 为空则用 config.goal 初始化
        if not self.state.goal:
            self.state.goal = config.goal

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #
    def run(self) -> LoopResult:
        """执行自治循环，返回 :class:`LoopResult`。"""
        result = LoopResult()
        # 首先检查暂停标志
        if self.state.is_paused():
            result.stop_reason = "loop-pause-all 已激活，循环未启动"
            result.final_state = self._state_snapshot()
            return result

        for i in range(self.config.max_iterations):
            iteration = self.state.next_iteration()
            # 预算检查：耗尽则停止
            if self.budget.should_stop():
                result.stop_reason = "预算耗尽（daily_cap 已达上限）"
                break
            # 预算降级：超过阈值时切 L1
            if self.budget.is_degraded() and self.config.level != TrustLevel.L1:
                self.config.level = TrustLevel.L1
                self.state.notes = f"预算达阈值 {self.budget.threshold}，降级为 L1 仅报告"

            # 执行 → 检查 → 记录
            step_output = self.execute_step(self.state)
            # 从 step_output 提取 token 用量并记录到预算（避免门控空转）
            if isinstance(step_output, dict):
                _usage = step_output.get("token_usage")
                if isinstance(_usage, int) and _usage > 0:
                    self.budget.record(_usage)
            goal_reached = self.check_result(self.state, step_output)
            self.memory.record(
                iteration=iteration,
                result=step_output if not isinstance(step_output, (str, int, float)) else step_output,
                metric=None,
                note=f"goal_reached={goal_reached}",
            )
            result.history.append(
                {
                    "iteration": iteration,
                    "level": self.config.level.value,
                    "goal_reached": goal_reached,
                    "budget_ratio": round(self.budget.ratio(), 3),
                }
            )

            if goal_reached:
                result.success = True
                result.stop_reason = f"目标达成（迭代 {iteration}）"
                break

            # 决策是否继续
            if not self.decide_continue(self.state):
                if not result.stop_reason:
                    result.stop_reason = "decide_continue 返回 False"
                break
        else:
            # for 循环正常结束（未 break）= 达到最大迭代数
            result.stop_reason = result.stop_reason or f"达到最大迭代数 {self.config.max_iterations}"

        result.iterations = self.state.iteration
        result.final_state = self._state_snapshot()
        self.state.update(iteration=self.state.iteration, success=result.success)
        return result

    # ------------------------------------------------------------------ #
    # 三步：执行 → 检查 → 决策
    # ------------------------------------------------------------------ #
    def execute_step(self, state: State) -> Any:
        """执行单次迭代的主体。

        优先使用注入的 ``execute_fn``；若未注入则返回占位结果。
        """
        if self._execute_fn is not None:
            return self._execute_fn(state)
        # 默认占位：L1 仅报告当前迭代
        return {"report": f"迭代 {state.iteration}：L1 仅报告模式，无执行体"}

    def check_result(self, state: State, result: Any) -> bool:
        """检查结果是否达成目标（stop_condition）。

        优先使用注入的 ``check_fn``；否则使用默认检查。
        """
        if self._check_fn is not None:
            return bool(self._check_fn(state, result))
        # 默认检查：无 stop_condition 时认为未达成（需继续迭代）
        if self.config.stop_condition is None:
            return False
        # 若结果是真值则视为达成
        return bool(result)

    def decide_continue(self, state: State) -> bool:
        """决策是否继续下一次迭代。

        综合考虑：暂停标志、预算、最大迭代数。优先使用注入的 ``decide_fn``。
        """
        if state.is_paused():
            return False
        if self.budget.should_stop():
            return False
        if self._decide_fn is not None:
            return bool(self._decide_fn(state))
        # 默认：只要还没到 max_iterations 就继续（for 循环已控制上限）
        return True

    # ------------------------------------------------------------------ #
    # 便捷方法
    # ------------------------------------------------------------------ #
    def _state_snapshot(self) -> dict[str, Any]:
        """生成当前状态快照（用于 LoopResult）。"""
        return {
            "iteration": self.state.iteration,
            "goal": self.state.goal,
            "level": self.config.level.value,
            "budget_spent": self.budget.spent,
            "budget_ratio": round(self.budget.ratio(), 3),
            "best_metric": self.memory.best_metric,
            "paused": self.state.is_paused(),
        }

    def pause(self, reason: str = "loop-pause-all") -> None:
        """暂停循环（设置 loop-pause-all 标志）。"""
        self.state.mark_paused(reason)

    def resume(self) -> None:
        """恢复循环（清除暂停标志）。"""
        self.state.clear_paused()

    def __repr__(self) -> str:
        return (
            f"<Loop goal={self.config.goal!r} level={self.config.level.value} "
            f"max_iter={self.config.max_iterations}>"
        )
