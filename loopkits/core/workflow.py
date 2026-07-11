"""WorkFlow 原语：有向图步骤串联。

WorkFlow 将多个步骤（Step）按顺序串联，每个步骤可调用不同 Agent 或 Service。
作为 Loop 的执行体（``Loop`` 的 ``execute_step`` 可直接调用
``WorkFlow.execute(context)``）。

特性：

- **重试策略**：``RetryPolicy(max_retries, backoff)``，失败后按指数退避重试。
- **回退**：步骤可配置 ``fallback`` 可调用对象，重试耗尽后调用。
- **上下文传递**：步骤间通过共享 ``context`` dict 传递数据。
- **顺序执行**：当前实现为有序列表（线性 DAG），满足首批模式需求。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from pydantic import BaseModel, Field

__all__ = ["RetryPolicy", "Step", "WorkFlow", "StepResult", "WorkflowResult"]


class RetryPolicy(BaseModel):
    """重试策略。

    Attributes:
        max_retries: 最大重试次数（不含首次执行）。
        backoff: 退避基础秒数，每次重试等待 ``backoff * (2 ** attempt)``。
    """

    max_retries: int = 0
    backoff: float = 1.0


class StepResult(BaseModel):
    """单步骤执行结果。"""

    name: str
    success: bool
    output: Any = None
    error: str = ""
    attempts: int = 1


class WorkflowResult(BaseModel):
    """WorkFlow 整体执行结果。"""

    success: bool
    context: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepResult] = Field(default_factory=list)
    failed_step: str | None = None


class Step:
    """工作流步骤。

    Args:
        name: 步骤名称。
        action: 执行函数，签名为 ``action(context: dict) -> Any``。
        inputs: 需要从 context 读取的键列表（仅用于声明，不强制）。
        outputs: 执行结果存入 context 的键名；为空则不存。
        retry_policy: 重试策略。
        fallback: 重试耗尽后的回退函数，签名为 ``fallback(context, error) -> Any``。
    """

    def __init__(
        self,
        name: str,
        action: Callable[[dict[str, Any]], Any],
        inputs: list[str] | None = None,
        outputs: str | None = None,
        retry_policy: RetryPolicy | None = None,
        fallback: Callable[[dict[str, Any], str], Any] | None = None,
    ):
        self.name = name
        self.action = action
        self.inputs = inputs or []
        self.outputs = outputs
        self.retry_policy = retry_policy or RetryPolicy()
        self.fallback = fallback

    def execute(self, context: dict[str, Any]) -> StepResult:
        """执行本步骤，按重试策略处理失败。"""
        last_error = ""
        attempts = 0
        max_attempts = self.retry_policy.max_retries + 1
        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                result = self.action(context)
                # 将结果写入 context
                if self.outputs:
                    context[self.outputs] = result
                return StepResult(
                    name=self.name,
                    success=True,
                    output=result,
                    attempts=attempts,
                )
            except Exception as exc:  # noqa: BLE001 — 工作流需捕获步骤异常
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < max_attempts - 1:
                    # 指数退避
                    wait = self.retry_policy.backoff * (2 ** attempt)
                    if wait > 0:
                        time.sleep(wait)
        # 重试耗尽，尝试回退
        if self.fallback is not None:
            try:
                result = self.fallback(context, last_error)
                if self.outputs:
                    context[self.outputs] = result
                return StepResult(
                    name=self.name,
                    success=True,
                    output=result,
                    error=f"回退成功：{last_error}",
                    attempts=attempts,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = f"回退也失败：{type(exc).__name__}: {exc}"
        return StepResult(
            name=self.name,
            success=False,
            error=last_error,
            attempts=attempts,
        )

    def __repr__(self) -> str:
        return f"<Step name={self.name!r}>"


class WorkFlow:
    """工作流：有序步骤串联。

    Args:
        name: 工作流名称。
        steps: 有序步骤列表。
    """

    def __init__(self, name: str = "", steps: list[Step] | None = None):
        self.name = name or "workflow"
        self.steps: list[Step] = steps or []

    def add_step(self, step: Step) -> "WorkFlow":
        """追加一个步骤，返回自身以支持链式调用。"""
        self.steps.append(step)
        return self

    def execute(self, context: dict[str, Any] | None = None) -> WorkflowResult:
        """按顺序执行所有步骤。

        任一步骤失败且无成功回退时，停止后续步骤并返回失败结果。
        """
        ctx = context if context is not None else {}
        results: list[StepResult] = []
        for step in self.steps:
            result = step.execute(ctx)
            results.append(result)
            if not result.success:
                return WorkflowResult(
                    success=False,
                    context=ctx,
                    steps=results,
                    failed_step=step.name,
                )
        return WorkflowResult(success=True, context=ctx, steps=results)

    def __call__(self, context: dict[str, Any] | None = None) -> WorkflowResult:
        """使 WorkFlow 可直接调用（便于作为 Loop 执行体）。"""
        return self.execute(context)

    def __repr__(self) -> str:
        return f"<WorkFlow name={self.name!r} steps={len(self.steps)}>"
