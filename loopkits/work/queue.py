"""任务队列与批量调度。

Work 模式的任务队列：单任务暂停不阻塞其他任务。每个任务有独立的状态
（PENDING / RUNNING / PAUSED / DONE / FAILED），Corrector 触发 PAUSE
时仅暂停当前任务，队列继续处理下一个 PENDING 任务。

用法::

    q = TaskQueue()
    q.add(Task(id="t1", name="发送周报", payload={...}))
    q.add(Task(id="t2", name="分类邮件", payload={...}))
    t = q.next()           # 取下一个 PENDING 任务
    q.mark_running(t.id)   # 标记为运行中
    q.mark_done(t.id, result={"ok": True}, confidence=0.95)
    print(q.to_markdown())
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["TaskStatus", "Task", "TaskQueue"]


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    PENDING = "PENDING"    # 待处理
    RUNNING = "RUNNING"    # 执行中
    PAUSED = "PAUSED"      # 已暂停（等待人工介入）
    DONE = "DONE"          # 已完成
    FAILED = "FAILED"      # 已失败


# 状态对应的 Markdown 图标
_STATUS_ICONS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "⬜",
    TaskStatus.RUNNING: "🔄",
    TaskStatus.PAUSED: "⏸️",
    TaskStatus.DONE: "✅",
    TaskStatus.FAILED: "❌",
}


class Task(BaseModel):
    """任务模型。

    Attributes:
        id: 任务唯一标识。
        name: 任务名称（人可读）。
        payload: 任务负载数据（dict）。
        status: 任务状态。
        result: 执行结果（DONE 后填充）。
        confidence: 结果置信度（0-1）。
        created_at: 创建时间（ISO 8601 UTC）。
        paused_reason: 暂停原因（PAUSED 时填充）。
        error: 失败原因（FAILED 时填充）。
    """

    id: str
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    confidence: float = 0.0
    created_at: str = Field(default_factory=_now_iso)
    paused_reason: str = ""
    error: str = ""


class TaskQueue:
    """任务队列：单任务暂停不阻塞其他。

    所有任务按入队顺序排列。``next()`` 取下一个 PENDING 任务；
    ``mark_paused()`` 暂停某任务后，``next()`` 会跳过它继续取下一个 PENDING。
    """

    def __init__(self) -> None:
        self.tasks: list[Task] = []

    # ------------------------------------------------------------------ #
    # 入队与出队
    # ------------------------------------------------------------------ #
    def add(self, task: Task) -> None:
        """将任务入队。"""
        self.tasks.append(task)

    def next(self) -> Task | None:
        """取下一个 PENDING 任务（不改变状态，需调用方手动 mark_running）。"""
        for task in self.tasks:
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def get(self, task_id: str) -> Task | None:
        """按 ID 获取任务。"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    # ------------------------------------------------------------------ #
    # 状态变更
    # ------------------------------------------------------------------ #
    def mark_running(self, task_id: str) -> bool:
        """标记任务为运行中。返回是否成功。"""
        task = self.get(task_id)
        if task is None or task.status != TaskStatus.PENDING:
            return False
        task.status = TaskStatus.RUNNING
        return True

    def mark_done(
        self,
        task_id: str,
        result: Any,
        confidence: float = 1.0,
    ) -> bool:
        """标记任务为已完成。返回是否成功。"""
        task = self.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.DONE
        task.result = result
        task.confidence = confidence
        task.paused_reason = ""
        task.error = ""
        return True

    def mark_paused(self, task_id: str, reason: str = "") -> bool:
        """标记任务为已暂停。返回是否成功。"""
        task = self.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.PAUSED
        task.paused_reason = reason
        return True

    def mark_failed(self, task_id: str, error: str = "") -> bool:
        """标记任务为已失败。返回是否成功。"""
        task = self.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.FAILED
        task.error = error
        return True

    def resume(self, task_id: str) -> bool:
        """恢复暂停的任务（将状态改回 PENDING，等待 next() 重新取出）。

        返回是否成功。仅 PAUSED 状态的任务可恢复。
        """
        task = self.get(task_id)
        if task is None or task.status != TaskStatus.PAUSED:
            return False
        task.status = TaskStatus.PENDING
        task.paused_reason = ""
        return True

    # ------------------------------------------------------------------ #
    # 统计与查询
    # ------------------------------------------------------------------ #
    def pending_count(self) -> int:
        """待处理任务数。"""
        return sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

    def done_count(self) -> int:
        """已完成任务数。"""
        return sum(1 for t in self.tasks if t.status == TaskStatus.DONE)

    def paused_count(self) -> int:
        """已暂停任务数。"""
        return sum(1 for t in self.tasks if t.status == TaskStatus.PAUSED)

    def failed_count(self) -> int:
        """已失败任务数。"""
        return sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)

    def running_count(self) -> int:
        """运行中任务数。"""
        return sum(1 for t in self.tasks if t.status == TaskStatus.RUNNING)

    def paused(self) -> list[Task]:
        """获取所有暂停的任务（供用户处理）。"""
        return [t for t in self.tasks if t.status == TaskStatus.PAUSED]

    def all(self) -> list[Task]:
        """获取所有任务。"""
        return list(self.tasks)

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def to_markdown(self) -> str:
        """渲染队列状态为 Markdown。"""
        if not self.tasks:
            return "# Task Queue\n\n（队列为空）\n"

        total = len(self.tasks)
        lines = [
            "# Task Queue",
            "",
            "## 概览",
            "",
            f"- 总数：{total}",
            f"- 待处理：{self.pending_count()}",
            f"- 运行中：{self.running_count()}",
            f"- 已暂停：{self.paused_count()}",
            f"- 已完成：{self.done_count()}",
            f"- 已失败：{self.failed_count()}",
            "",
            "## 任务列表",
            "",
        ]
        for task in self.tasks:
            icon = _STATUS_ICONS.get(task.status, "•")
            line = f"- {icon} **[{task.status.value}]** `{task.id}` {task.name}"
            if task.status == TaskStatus.PAUSED and task.paused_reason:
                line += f"\n  - 暂停原因：{task.paused_reason}"
            elif task.status == TaskStatus.DONE:
                line += f"\n  - 置信度：{task.confidence:.2f}"
            elif task.status == TaskStatus.FAILED and task.error:
                line += f"\n  - 错误：{task.error}"
            lines.append(line)
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.tasks)

    def __repr__(self) -> str:
        return (
            f"<TaskQueue total={len(self.tasks)} "
            f"pending={self.pending_count()} "
            f"done={self.done_count()} "
            f"paused={self.paused_count()}>"
        )
