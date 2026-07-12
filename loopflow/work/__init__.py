"""Work 模式（办公职员）：Comments + Corrector 机制。

Work 模式是 Code 模式的高级封装，面向办公职员。核心机制：

- **Comments 轨迹**：每个决策都有依据，每个暂停都有提问和下一步建议
- **Corrector 阈值**：低置信度时暂停而非盲目执行
- **任务队列**：单任务暂停不阻塞其他任务
- **编排器**：封装 Code 循环 + WorkFlow + 服务

模块结构：

- :mod:`loopflow.work.comments` — 结构化注释轨迹（CommentType / Comment / CommentTrail）
- :mod:`loopflow.work.corrector` — Work 模式校正器（WorkCorrector / CorrectorAction）
- :mod:`loopflow.work.queue` — 任务队列（TaskQueue / Task / TaskStatus）
- :mod:`loopflow.work.orchestrator` — 编排器（WorkOrchestrator / WorkConfig）
- :mod:`loopflow.work.templates` — 常见任务模板（周报 / 邮件分类 / 日程整理）

用法::

    from loopflow.work import (
        CommentTrail, CommentType, WorkCorrector,
        TaskQueue, WorkOrchestrator, WorkConfig,
    )
    from loopflow.work.templates import weekly_report_template

    cfg = weekly_report_template()
    orch = WorkOrchestrator(cfg)
    result = orch.run_batch([Task(id="w1", name="周报", payload={})])
    print(orch.to_report())
"""

from loopflow.work.comments import Comment, CommentTrail, CommentType
from loopflow.work.corrector import ActionType, CorrectorAction, WorkCorrector
from loopflow.work.orchestrator import (
    BatchResult,
    TaskResult,
    WorkConfig,
    WorkOrchestrator,
)
from loopflow.work.queue import Task, TaskQueue, TaskStatus

__all__ = [
    # Comments
    "CommentType",
    "Comment",
    "CommentTrail",
    # Corrector
    "ActionType",
    "CorrectorAction",
    "WorkCorrector",
    # Queue
    "TaskStatus",
    "Task",
    "TaskQueue",
    # Orchestrator
    "WorkConfig",
    "TaskResult",
    "BatchResult",
    "WorkOrchestrator",
]
