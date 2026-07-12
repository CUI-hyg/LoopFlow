"""Work 模式编排器。

封装 Code 模式循环 + WorkFlow + 服务，提供面向办公职员的批量任务执行能力。
核心特性：

- **Comments 轨迹**：每个决策都有依据，每个暂停都有提问和下一步建议
- **Corrector 阈值**：低置信度时暂停而非盲目执行
- **单任务暂停不阻塞**：队列继续处理下一个 PENDING 任务

用法::

    from loopflow.work import WorkOrchestrator, WorkConfig, WorkCorrector
    from loopflow.work.templates import weekly_report_template

    cfg = weekly_report_template()
    orch = WorkOrchestrator(cfg)
    result = orch.run_batch([Task(id="w1", name="周报", payload={})])
    print(orch.to_report())
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from loopflow.core.workflow import WorkFlow
from loopflow.work.comments import Comment, CommentTrail, CommentType
from loopflow.work.corrector import ActionType, CorrectorAction, WorkCorrector
from loopflow.work.queue import Task, TaskQueue, TaskStatus

__all__ = [
    "WorkConfig",
    "TaskResult",
    "BatchResult",
    "WorkOrchestrator",
]


class WorkConfig(BaseModel):
    """Work 模式配置。

    Attributes:
        name: 配置名称。
        description: 配置描述。
        pattern_name: 可选，复用 Code 模式的模式名（如 ``changelog-drafter``）。
        workflow: 预构建的 WorkFlow（Step 串联）。
        services: 服务实例字典（键为服务名，值为 Service 对象）。
        required_services: 所需服务名列表（用于声明依赖）。
        corrector: Work 模式校正器。
        schedule: 调度描述（cron 表达式或 interval 描述，如 ``1d`` / ``0 9 * * 1``）。
    """

    name: str
    description: str = ""
    pattern_name: str | None = None
    workflow: WorkFlow
    services: dict[str, Any] = Field(default_factory=dict)
    required_services: list[str] = Field(default_factory=list)
    corrector: WorkCorrector = Field(default_factory=WorkCorrector)
    schedule: str = ""

    model_config = {"arbitrary_types_allowed": True}


class TaskResult(BaseModel):
    """单个任务执行结果。

    Attributes:
        task_id: 任务 ID。
        success: 是否成功完成。
        result: 执行结果。
        confidence: 结果置信度。
        action_type: Corrector 动作类型（PROCEED / PAUSE / CORRECT）。
        error: 错误信息（失败时填充）。
        paused: 是否已暂停。
    """

    task_id: str
    success: bool = False
    result: Any = None
    confidence: float = 0.0
    action_type: str = ""
    error: str = ""
    paused: bool = False


class BatchResult(BaseModel):
    """批量执行结果。

    Attributes:
        total: 任务总数。
        done: 已完成数。
        paused: 已暂停数。
        failed: 已失败数。
        task_results: 各任务的执行结果。
        comments: 批次期间生成的注释快照。
    """

    total: int = 0
    done: int = 0
    paused: int = 0
    failed: int = 0
    task_results: list[TaskResult] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)


class WorkOrchestrator:
    """Work 模式编排器：封装 Code 循环 + WorkFlow + 服务。

    Args:
        config: Work 模式配置。
    """

    def __init__(self, config: WorkConfig) -> None:
        self.config: WorkConfig = config
        self.comments: CommentTrail = CommentTrail()
        self.queue: TaskQueue = TaskQueue()

    # ------------------------------------------------------------------ #
    # 批量执行
    # ------------------------------------------------------------------ #
    def run_batch(self, tasks: list[Task]) -> BatchResult:
        """批量执行任务。

        遍历任务队列，每个任务：

        1. 通过 WorkFlow 执行任务（调用服务）
        2. 记录 DECISION + EVIDENCE 注释
        3. 用 Corrector 检查结果
        4. 如果 PAUSE：标记任务暂停，记录 QUESTION + NEXT_STEP，继续下一个（不阻塞）
        5. 如果 PROCEED：标记 DONE

        单任务暂停不阻塞其他任务。
        """
        # 入队
        for task in tasks:
            self.queue.add(task)

        task_results: list[TaskResult] = []
        # 逐个处理 PENDING 任务（暂停的任务自动跳过）
        while True:
            task = self.queue.next()
            if task is None:
                break
            result = self.run_single(task)
            task_results.append(result)

        return BatchResult(
            total=len(tasks),
            done=self.queue.done_count(),
            paused=self.queue.paused_count(),
            failed=self.queue.failed_count(),
            task_results=task_results,
            comments=list(self.comments.comments),
        )

    # ------------------------------------------------------------------ #
    # 单任务执行
    # ------------------------------------------------------------------ #
    def run_single(self, task: Task) -> TaskResult:
        """执行单个任务。

        步骤：

        1. 标记 RUNNING
        2. 通过 WorkFlow 执行
        3. 记录 DECISION + EVIDENCE 注释
        4. Corrector 检查
        5. 根据动作（PAUSE/CORRECT/PROCEED）更新状态
        """
        self.queue.mark_running(task.id)

        # 记录决策：开始执行
        self.comments.add(
            CommentType.DECISION,
            f"开始执行任务：{task.name}（payload keys: {list(task.payload.keys())}）",
            task_id=task.id,
            confidence=1.0,
        )

        # 执行 WorkFlow
        context: dict[str, Any] = {
            "task": task,
            "task_id": task.id,
            "task_name": task.name,
            "payload": task.payload,
            "services": self.config.services,
        }
        try:
            wf_result = self.config.workflow.execute(context)
        except Exception as exc:  # noqa: BLE001 — 工作流异常需捕获以免阻塞队列
            error_msg = f"工作流执行异常：{type(exc).__name__}: {exc}"
            self.queue.mark_failed(task.id, error=error_msg)
            self.comments.add(
                CommentType.EVIDENCE,
                error_msg,
                task_id=task.id,
                confidence=0.0,
            )
            return TaskResult(
                task_id=task.id,
                success=False,
                error=error_msg,
                action_type="FAILED",
            )

        # 工作流失败
        if not wf_result.success:
            failed_step = wf_result.failed_step or "unknown"
            step_error = ""
            for step_res in wf_result.steps:
                if not step_res.success:
                    step_error = step_res.error
                    break
            error_msg = f"工作流失败于步骤 [{failed_step}]：{step_error}"
            self.queue.mark_failed(task.id, error=error_msg)
            self.comments.add(
                CommentType.EVIDENCE,
                error_msg,
                task_id=task.id,
                confidence=0.0,
            )
            return TaskResult(
                task_id=task.id,
                success=False,
                error=error_msg,
                action_type="FAILED",
            )

        # 提取结果与置信度
        result = wf_result.context
        # confidence 缺失时默认 0.0（fail-closed，避免未知结果被高置信度放行）
        confidence = float(
            wf_result.context.get(
                "confidence",
                0.0,
            )
        )

        # 记录依据：执行结果
        result_summary = self._summarize_result(result)
        self.comments.add(
            CommentType.EVIDENCE,
            f"工作流执行成功。{result_summary}（置信度 {confidence:.2f}）",
            task_id=task.id,
            confidence=confidence,
        )

        # Corrector 检查
        action = self.config.corrector.check(task, result, confidence)
        self._handle_corrector_action(task, action, result=result, confidence=confidence)

        # 构造 TaskResult
        task_result = TaskResult(
            task_id=task.id,
            success=action.type == ActionType.PROCEED,
            result=result,
            confidence=confidence,
            action_type=action.type.value,
            paused=action.type in (ActionType.PAUSE, ActionType.CORRECT),
            error="" if action.type != ActionType.CORRECT else action.reason,
        )
        return task_result

    # ------------------------------------------------------------------ #
    # 暂停任务管理
    # ------------------------------------------------------------------ #
    def paused_tasks(self) -> list[Task]:
        """返回所有待人工处理的暂停任务。"""
        return self.queue.paused()

    def resume(self, task_id: str, decision: Any) -> TaskResult:
        """根据人工决策恢复暂停的任务。

        Args:
            task_id: 任务 ID。
            decision: 人工决策。可为字符串或字典：

                - ``"proceed"`` — 继续执行，标记为 DONE
                - ``"cancel"`` — 取消任务，标记为 FAILED
                - ``{"action": "proceed", "result": {...}, "confidence": 0.9}`` — 带结果继续
                - ``{"action": "correct", "result": {...}, "confidence": 0.95}`` — 带修正结果继续
                - ``{"action": "cancel", "reason": "..."}`` — 取消

        Returns:
            任务执行结果。
        """
        task = self.queue.get(task_id)
        if task is None:
            return TaskResult(
                task_id=task_id,
                success=False,
                error=f"任务 {task_id} 不存在",
            )
        if task.status != TaskStatus.PAUSED:
            return TaskResult(
                task_id=task_id,
                success=False,
                error=f"任务 {task_id} 状态为 {task.status.value}，非暂停状态，无法恢复",
            )

        # 规范化 decision
        if isinstance(decision, str):
            decision = {"action": decision}
        action = str(decision.get("action", "proceed")).lower()

        # 记录人工决策
        self.comments.add(
            CommentType.DECISION,
            f"人工决策：{action}（详情：{decision}）",
            task_id=task_id,
            author="human",
            confidence=float(decision.get("confidence", 1.0)),
        )

        if action == "cancel":
            reason = str(decision.get("reason", "人工取消"))
            self.queue.mark_failed(task_id, error=reason)
            self.comments.add(
                CommentType.INFO,
                f"任务已取消：{reason}",
                task_id=task_id,
                author="human",
            )
            return TaskResult(
                task_id=task_id,
                success=False,
                error=reason,
                action_type="CANCELLED",
            )

        # proceed 或 correct：标记为 DONE
        result = decision.get("result", task.result)
        confidence = float(decision.get("confidence", 1.0))
        self.queue.mark_done(task_id, result=result, confidence=confidence)

        # 解决该任务的所有待确认注释
        resolved_count = self.comments.resolve_for_task(task_id)
        self.comments.add(
            CommentType.INFO,
            f"任务已恢复并完成（置信度 {confidence:.2f}，解决 {resolved_count} 条待确认）",
            task_id=task_id,
            author="human",
            confidence=confidence,
        )

        return TaskResult(
            task_id=task_id,
            success=True,
            result=result,
            confidence=confidence,
            action_type=ActionType.PROCEED.value,
        )

    # ------------------------------------------------------------------ #
    # 报告
    # ------------------------------------------------------------------ #
    def to_report(self) -> str:
        """生成完整报告（含配置、队列状态、注释轨迹）。"""
        lines = [
            "# Work Mode Report",
            "",
            "## 配置",
            "",
            f"- **名称**：{self.config.name}",
        ]
        if self.config.description:
            lines.append(f"- **描述**：{self.config.description}")
        if self.config.pattern_name:
            lines.append(f"- **复用模式**：{self.config.pattern_name}")
        if self.config.schedule:
            lines.append(f"- **调度**：{self.config.schedule}")
        if self.config.required_services:
            lines.append(f"- **所需服务**：{', '.join(self.config.required_services)}")
        lines.append(f"- **Corrector 阈值**：{self.config.corrector.confidence_threshold:.2f}")
        lines.append("")

        lines.append("## 任务队列")
        lines.append("")
        lines.append(self.queue.to_markdown())
        lines.append("")

        lines.append("## 注释轨迹")
        lines.append("")
        lines.append(self.comments.to_markdown())

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    def _handle_corrector_action(
        self,
        task: Task,
        action: CorrectorAction,
        *,
        result: Any = None,
        confidence: float = 1.0,
    ) -> None:
        """根据 Corrector 动作更新任务状态并记录注释。"""
        if action.type == ActionType.PAUSE:
            # 暂停：记录 QUESTION + NEXT_STEP
            self.queue.mark_paused(task.id, reason=action.reason)
            self.comments.add(
                CommentType.QUESTION,
                action.question or "置信度不足，需人工确认",
                task_id=task.id,
                confidence=0.0,
            )
            self.comments.add(
                CommentType.NEXT_STEP,
                action.next_step or "建议人工审核后通过 resume() 恢复",
                task_id=task.id,
            )
            self.comments.add(
                CommentType.PENDING,
                f"任务已暂停：{action.reason}",
                task_id=task.id,
            )

        elif action.type == ActionType.CORRECT:
            # 校正：记录 EVIDENCE + NEXT_STEP（含建议）
            self.queue.mark_paused(task.id, reason=action.reason)
            suggestions_text = "\n".join(
                f"  - {s}" for s in action.suggestions
            ) if action.suggestions else "  - 无具体建议"
            self.comments.add(
                CommentType.EVIDENCE,
                f"结果偏离规范：{action.reason}\n修正建议：\n{suggestions_text}",
                task_id=task.id,
                confidence=0.5,
            )
            self.comments.add(
                CommentType.NEXT_STEP,
                action.next_step or "建议人工修正后通过 resume() 恢复",
                task_id=task.id,
            )
            self.comments.add(
                CommentType.PENDING,
                f"任务等待修正：{action.reason}",
                task_id=task.id,
            )

        else:  # PROCEED
            self.queue.mark_done(task.id, result=result, confidence=confidence)
            self.comments.add(
                CommentType.INFO,
                f"任务完成：{action.reason}",
                task_id=task.id,
                confidence=confidence,
            )

    @staticmethod
    def _summarize_result(result: Any) -> str:
        """生成结果的简要描述（用于 EVIDENCE 注释）。"""
        if result is None:
            return "无结果"
        if isinstance(result, dict):
            keys = list(result.keys())
            # 尝试提取关键信息
            parts: list[str] = []
            if "commits" in result:
                parts.append(f"扫描 {len(result['commits'])} 个提交")
            if "emails" in result:
                parts.append(f"处理 {len(result['emails'])} 封邮件")
            if "events" in result:
                parts.append(f"读取 {len(result['events'])} 个日程")
            if "report" in result:
                parts.append("已生成报告")
            if "draft" in result:
                parts.append("已生成草案")
            if "sent" in result:
                parts.append("已发送" if result.get("sent") else "发送失败（dry_run）")
            if not parts:
                parts.append(f"结果键：{keys[:5]}")
            return "；".join(parts)
        return f"结果类型：{type(result).__name__}"

    def __repr__(self) -> str:
        return (
            f"<WorkOrchestrator config={self.config.name!r} "
            f"queue={self.queue!r} "
            f"comments={self.comments!r}>"
        )
