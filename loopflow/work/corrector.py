"""Work 模式专用 Corrector Agent。

继承 :class:`loopflow.core.agent.Corrector`，扩展为 Work 模式的校正器。
核心机制：**置信度阈值** — 低于阈值时暂停任务（而非盲目执行），并生成
QUESTION + NEXT_STEP 注释供人工介入。

三类动作：

- ``PAUSE`` — 置信度低于阈值，暂停任务，生成提问与下一步建议
- ``CORRECT`` — 结果偏离规范（如含错误标记），建议修正
- ``PROCEED`` — 置信度充足且结果正常，继续执行
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from loopflow.core.agent import Corrector

__all__ = ["ActionType", "CorrectorAction", "WorkCorrector"]


class ActionType(str, Enum):
    """Corrector 动作类型。"""

    PAUSE = "PAUSE"        # 暂停：置信度不足，需人工介入
    CORRECT = "CORRECT"    # 校正：结果偏离规范，建议修正
    PROCEED = "PROCEED"    # 继续：置信度充足且结果正常


class CorrectorAction(BaseModel):
    """Corrector 的检查结果。

    Attributes:
        type: 动作类型（PAUSE / CORRECT / PROCEED）。
        reason: 触发该动作的原因。
        suggestions: 修正建议列表（CORRECT 时非空）。
        question: 给用户的提问（PAUSE 时非空）。
        next_step: 下一步建议（PAUSE / CORRECT 时非空）。
    """

    type: ActionType
    reason: str = ""
    suggestions: list[str] = Field(default_factory=list)
    question: str = ""
    next_step: str = ""


class WorkCorrector(Corrector):
    """Work 模式校正器。

    继承 :class:`~loopflow.core.agent.Corrector`，复用其 ``confidence_threshold``
    与 ``role`` 属性。核心方法 :meth:`check` 根据置信度与结果质量返回
    :class:`CorrectorAction`。

    Args:
        name: Corrector 名称。
        confidence_threshold: 置信度阈值，低于此值触发暂停（默认 0.7）。
    """

    def __init__(
        self,
        name: str = "work-corrector",
        confidence_threshold: float = 0.7,
    ) -> None:
        super().__init__(name=name, confidence_threshold=confidence_threshold)

    # ------------------------------------------------------------------ #
    # 核心方法
    # ------------------------------------------------------------------ #
    def check(
        self,
        task: Any,
        result: Any,
        confidence: float,
    ) -> CorrectorAction:
        """检查任务结果，返回 PAUSE / CORRECT / PROCEED 动作。

        判定优先级：

        1. ``confidence < threshold`` → **PAUSE**（生成 QUESTION + NEXT_STEP）
        2. 结果偏离规范（含错误标记） → **CORRECT**（建议修正）
        3. 否则 → **PROCEED**

        Args:
            task: 任务对象或任务 ID 字符串。
            result: 任务执行结果。
            confidence: 结果置信度（0-1）。
        """
        task_id = self._task_id(task)

        # 1. 低置信度 → PAUSE
        if confidence < self.confidence_threshold:
            question = self.propose_question(
                task, f"置信度 {confidence:.2f} 低于阈值 {self.confidence_threshold:.2f}"
            )
            next_step = self.propose_next_step(task, result)
            return CorrectorAction(
                type=ActionType.PAUSE,
                reason=(
                    f"置信度 {confidence:.2f} 低于阈值 {self.confidence_threshold:.2f}，"
                    f"暂停任务 {task_id} 等待人工确认"
                ),
                suggestions=[],
                question=question,
                next_step=next_step,
            )

        # 2. 结果偏离规范 → CORRECT
        deviation = self._detect_deviation(result)
        if deviation is not None:
            suggestions = self._generate_suggestions(result, deviation)
            next_step = self.propose_next_step(task, result)
            return CorrectorAction(
                type=ActionType.CORRECT,
                reason=f"任务 {task_id} 结果偏离规范：{deviation}",
                suggestions=suggestions,
                question="",
                next_step=next_step,
            )

        # 3. 正常 → PROCEED
        return CorrectorAction(
            type=ActionType.PROCEED,
            reason=f"置信度 {confidence:.2f} 充足且结果符合规范，继续执行任务 {task_id}",
            suggestions=[],
            question="",
            next_step="",
        )

    # ------------------------------------------------------------------ #
    # 提问与下一步建议生成
    # ------------------------------------------------------------------ #
    def propose_question(self, task: Any, uncertainty: str) -> str:
        """生成给用户的提问。

        Args:
            task: 任务对象或任务 ID 字符串。
            uncertainty: 不确定性描述。
        """
        task_id = self._task_id(task)
        task_name = self._task_name(task)
        return (
            f"任务 [{task_id}] {task_name} 存在不确定性：{uncertainty}。"
            f"请确认如何处理？（可选：继续执行 / 修正结果 / 取消任务）"
        )

    def propose_next_step(self, task: Any, result: Any) -> str:
        """生成下一步建议。

        Args:
            task: 任务对象或任务 ID 字符串。
            result: 当前执行结果。
        """
        task_id = self._task_id(task)
        return (
            f"建议人工审核任务 [{task_id}] 的结果后，通过 "
            f"orchestrator.resume(task_id='{task_id}', decision=...) 恢复执行。"
        )

    # ------------------------------------------------------------------ #
    # Agent 接口兼容
    # ------------------------------------------------------------------ #
    def execute(self, task: Any) -> CorrectorAction:
        """兼容 :class:`~loopflow.core.agent.Agent` 接口。

        从 task dict 中提取 ``result`` 与 ``confidence``，调用 :meth:`check`。
        """
        if isinstance(task, dict):
            return self.check(
                task=task.get("id", task.get("task_id", "")),
                result=task.get("result"),
                confidence=float(task.get("confidence", 1.0)),
            )
        return self.check(task=task, result=None, confidence=1.0)

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _task_id(task: Any) -> str:
        """从 task 对象或字符串中提取任务 ID。"""
        if isinstance(task, str):
            return task
        return str(getattr(task, "id", "") or getattr(task, "task_id", "") or task)

    @staticmethod
    def _task_name(task: Any) -> str:
        """从 task 对象中提取任务名称。"""
        if isinstance(task, str):
            return ""
        return str(getattr(task, "name", "") or "")

    @staticmethod
    def _detect_deviation(result: Any) -> str | None:
        """检测结果是否偏离规范，返回偏离描述（无偏离返回 None）。

        检测规则：

        - ``result`` 为 None → 「结果为空」
        - ``result`` 是 dict 且含 ``error`` 非空键 → 「执行报错」
        - ``result`` 是 dict 且 ``status`` 为 failed/error → 「状态异常」
        - ``result`` 是 dict 且 ``ok`` 为 False → 「结果标记为失败」
        - ``result`` 是 dict 且 ``category`` 为 unknown → 「分类结果未知」
        """
        if result is None:
            return "结果为空"

        if isinstance(result, dict):
            # error 字段
            err = result.get("error")
            if err:
                return f"执行报错：{err}"
            # status 字段
            status = result.get("status")
            if status in ("failed", "error", "FAILED", "ERROR"):
                return f"状态异常：{status}"
            # ok 字段
            ok = result.get("ok")
            if ok is False:
                return "结果标记为失败（ok=False）"
            # category 字段
            category = result.get("category")
            if category in ("unknown", "UNKNOWN", "unclear", "uncertain"):
                return f"分类结果未知：{category}"

        return None

    def _generate_suggestions(self, result: Any, deviation: str) -> list[str]:
        """根据偏离情况生成修正建议。"""
        suggestions: list[str] = []
        if isinstance(result, dict):
            if result.get("error"):
                suggestions.append(f"检查错误信息并修复：{result['error']}")
            if result.get("category") in ("unknown", "UNKNOWN"):
                suggestions.append("补充上下文信息后重新分类，或人工指定分类")
            if result.get("ok") is False:
                suggestions.append("检查失败原因，修正后重试")
        if not suggestions:
            suggestions.append(f"根据偏离原因修正：{deviation}")
        suggestions.append("修正后通过 orchestrator.resume() 恢复任务")
        return suggestions

    def __repr__(self) -> str:
        return (
            f"<WorkCorrector name={self.name!r} "
            f"threshold={self.confidence_threshold:.2f}>"
        )
