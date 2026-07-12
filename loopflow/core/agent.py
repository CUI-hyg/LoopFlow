"""Agent 基类与四角色。

Agent 是 LoopFlow 公式中的执行单元。借鉴 loop-engineering 的 Maker / Checker
分裂思想（「写代码的 agent 不能给自己的作业打分」），扩展为四角色：

- **Maker**：产出方案 / 代码 / 内容
- **Checker**：校验产出是否符合规范
- **Corrector**：当不确定或偏离时提出问题 / 建议（Work 模式核心）
- **Verifier**：验证最终结果是否达标

Agent 可被 Loop 和 WorkFlow 调用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

__all__ = ["AgentRole", "Agent", "Maker", "Checker", "Corrector", "Verifier"]


class AgentRole(str, Enum):
    """Agent 角色枚举。"""

    MAKER = "maker"            # 产出
    CHECKER = "checker"        # 校验
    CORRECTOR = "corrector"    # 校正（Work 模式）
    VERIFIER = "verifier"      # 验证


class Agent(ABC):
    """Agent 抽象基类。

    所有 Agent 持有 ``role`` 与 ``name``，必须实现 :meth:`execute`。
    :meth:`can_handle` 用于判断该 Agent 是否能处理给定任务（默认 True，子类
    可按 ``task`` 的 ``type`` / ``role`` 字段过滤）。

    Args:
        name: Agent 名称。
        handler: 可选的实际处理函数（若提供则 ``execute`` 直接调用它，便于
            快速注入业务逻辑而无需继承子类）。
    """

    role: AgentRole = AgentRole.MAKER

    def __init__(self, name: str = "", handler: Callable[[Any], Any] | None = None):
        self.name = name or self.__class__.__name__
        self._handler = handler

    @abstractmethod
    def execute(self, task: Any) -> Any:
        """执行任务，返回产出结果。子类必须实现。"""

    def can_handle(self, task: Any) -> bool:
        """判断本 Agent 是否能处理该任务。

        默认实现：若 ``task`` 是 dict 且含 ``role`` 键，则要求匹配；否则
        始终返回 True。
        """
        if isinstance(task, dict) and "role" in task:
            return str(task["role"]).lower() == self.role.value
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} role={self.role.value}>"


class Maker(Agent):
    """产出者：产出方案 / 代码 / 内容。

    若构造时传入 ``handler``，则 ``execute`` 直接调用它；否则子类需重写
    :meth:`execute`。
    """

    role = AgentRole.MAKER

    def execute(self, task: Any) -> Any:
        if self._handler is not None:
            return self._handler(task)
        raise NotImplementedError(
            f"Maker '{self.name}' 未提供 handler，且未重写 execute()"
        )


class Checker(Agent):
    """校验者：校验产出是否符合规范。

    返回 :class:`CheckResult` 或布尔值，表示产出是否通过校验及问题描述。
    """

    role = AgentRole.CHECKER

    def execute(self, task: Any) -> Any:
        if self._handler is not None:
            return self._handler(task)
        # 默认实现：task 含 'output' 与 'spec' 时做简单包含检查
        if isinstance(task, dict) and "output" in task:
            spec = task.get("spec", "")
            output = task.get("output", "")
            if spec and isinstance(output, str) and spec not in output:
                return CheckResult(passed=False, issues=[f"产出未包含规范要求：{spec}"])
            return CheckResult(passed=True, issues=[])
        return CheckResult(passed=True, issues=["无校验规则，默认通过"])


class Corrector(Agent):
    """校正者：当不确定或偏离时提出问题 / 建议（Work 模式核心）。

    正确用法：在关键决策节点，Corrector 检查置信度（``task['confidence']``），
    若低于阈值则暂停并返回 :class:`Correction`，包含问题与候选方案。
    """

    role = AgentRole.CORRECTOR

    def __init__(
        self,
        name: str = "",
        handler: Callable[[Any], Any] | None = None,
        confidence_threshold: float = 0.7,
    ):
        super().__init__(name=name, handler=handler)
        self.confidence_threshold = confidence_threshold

    def execute(self, task: Any) -> Any:
        if self._handler is not None:
            return self._handler(task)
        # 默认实现：基于置信度判断是否需要人工校正
        confidence = 1.0
        if isinstance(task, dict):
            confidence = float(task.get("confidence", 1.0))
        if confidence < self.confidence_threshold:
            return Correction(
                paused=True,
                reason=f"置信度 {confidence:.2f} 低于阈值 {self.confidence_threshold}",
                suggestions=task.get("candidates", []) if isinstance(task, dict) else [],
            )
        return Correction(paused=False, reason="置信度充足，无需校正", suggestions=[])


class Verifier(Agent):
    """验证者：验证最终结果是否达标。

    与 Checker 的区别：Checker 校验中间产出是否符合规范，Verifier 验证
    最终结果是否达成 Loop 的目标（stop_condition）。
    """

    role = AgentRole.VERIFIER

    def execute(self, task: Any) -> Any:
        if self._handler is not None:
            return self._handler(task)
        # 默认实现：task 含 'result' 与 'goal' 时做简单匹配
        if isinstance(task, dict) and "result" in task and "goal" in task:
            result = str(task.get("result", ""))
            goal = str(task.get("goal", ""))
            achieved = goal.lower() in result.lower() if goal else True
            return VerifyResult(achieved=achieved, detail=f"目标 '{goal}' {'已达成' if achieved else '未达成'}")
        return VerifyResult(achieved=True, detail="无验证条件，默认达成")


# ---------------------------------------------------------------------- #
# 结果数据模型
# ---------------------------------------------------------------------- #
class CheckResult(BaseModel):
    """Checker 的校验结果。"""

    passed: bool
    issues: list[str] = Field(default_factory=list)


class Correction(BaseModel):
    """Corrector 的校正建议。"""

    paused: bool
    reason: str
    suggestions: list[Any] = Field(default_factory=list)


class VerifyResult(BaseModel):
    """Verifier 的验证结果。"""

    achieved: bool
    detail: str = ""
