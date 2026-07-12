"""结构化注释轨迹（Work 模式核心）。

Comments 机制记录 Work 模式每个任务的处理过程：每个决策都有依据，
每个暂停都有提问和下一步建议。注释按任务分组，形成可追溯的时间线。

CommentType 枚举覆盖六类常见注释：

- ``DECISION`` — 决策（如「将邮件分类为高优先级」）
- ``EVIDENCE`` — 依据（如「邮件包含紧急关键词」）
- ``PENDING`` — 待确认（如「需人工复核分类结果」）
- ``QUESTION`` — 提问（如「无法确定优先级，候选: 高/中」）
- ``NEXT_STEP`` — 下一步建议（如「建议人工审核后恢复执行」）
- ``INFO`` — 信息（如「工作流执行成功，耗时 0.3s」）
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["CommentType", "Comment", "CommentTrail"]


class CommentType(str, Enum):
    """注释类型枚举。"""

    DECISION = "DECISION"      # 决策
    EVIDENCE = "EVIDENCE"      # 依据
    PENDING = "PENDING"        # 待确认
    QUESTION = "QUESTION"      # 提问
    NEXT_STEP = "NEXT_STEP"    # 下一步建议
    INFO = "INFO"              # 信息


# 类型对应的 Markdown 图标，便于人可读渲染
_TYPE_ICONS: dict[CommentType, str] = {
    CommentType.DECISION: "📋",
    CommentType.EVIDENCE: "🔍",
    CommentType.PENDING: "⏳",
    CommentType.QUESTION: "❓",
    CommentType.NEXT_STEP: "➡️",
    CommentType.INFO: "ℹ️",
}


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Comment(BaseModel):
    """单条结构化注释。

    Attributes:
        id: 注释唯一标识（UUID）。
        type: 注释类型。
        timestamp: ISO 8601 时间戳（UTC）。
        task_id: 所属任务 ID。
        content: 注释内容。
        author: 作者（``agent`` 或 ``human``）。
        confidence: 置信度（0-1）。
        resolved: 是否已解决（待确认项被人工处理后标记为 True）。
    """

    id: str
    type: CommentType
    timestamp: str
    task_id: str
    content: str
    author: str = "agent"
    confidence: float = 1.0
    resolved: bool = False


class CommentTrail:
    """注释轨迹：按任务分组的时间线。

    Work 模式的核心审计机制。每个任务的决策、依据、提问、下一步建议
    都记录在此，形成可追溯的处理过程。

    用法::

        trail = CommentTrail()
        trail.add(CommentType.DECISION, "将邮件分类为高优先级",
                  task_id="t1", confidence=0.9)
        trail.add(CommentType.QUESTION, "无法确定优先级",
                  task_id="t2", confidence=0.5)
        print(trail.to_markdown())
        for c in trail.pending():
            print(c)
    """

    def __init__(self) -> None:
        self.comments: list[Comment] = []

    # ------------------------------------------------------------------ #
    # 添加与查询
    # ------------------------------------------------------------------ #
    def add(
        self,
        type: CommentType,
        content: str,
        task_id: str,
        confidence: float = 1.0,
        author: str = "agent",
    ) -> Comment:
        """添加一条注释并返回该注释。

        Args:
            type: 注释类型。
            content: 注释内容。
            task_id: 所属任务 ID。
            confidence: 置信度（0-1）。
            author: 作者（``agent`` 或 ``human``）。
        """
        comment = Comment(
            id=str(uuid.uuid4()),
            type=type,
            timestamp=_now_iso(),
            task_id=task_id,
            content=content,
            author=author,
            confidence=confidence,
            resolved=False,
        )
        self.comments.append(comment)
        return comment

    def for_task(self, task_id: str) -> list[Comment]:
        """获取某任务的所有注释（按时间排序）。"""
        return sorted(
            [c for c in self.comments if c.task_id == task_id],
            key=lambda c: c.timestamp,
        )

    def pending(self) -> list[Comment]:
        """获取所有未解决的待确认/提问项。"""
        return [
            c
            for c in self.comments
            if c.type in (CommentType.PENDING, CommentType.QUESTION)
            and not c.resolved
        ]

    def resolve(self, comment_id: str) -> bool:
        """标记某条注释为已解决。返回是否成功找到并标记。"""
        for c in self.comments:
            if c.id == comment_id:
                c.resolved = True
                return True
        return False

    def resolve_for_task(self, task_id: str) -> int:
        """标记某任务的所有待确认/提问项为已解决。返回标记数量。"""
        count = 0
        for c in self.comments:
            if (
                c.task_id == task_id
                and c.type in (CommentType.PENDING, CommentType.QUESTION)
                and not c.resolved
            ):
                c.resolved = True
                count += 1
        return count

    # ------------------------------------------------------------------ #
    # 序列化
    # ------------------------------------------------------------------ #
    def to_markdown(self) -> str:
        """渲染为可读 Markdown（按任务分组，含时间线）。"""
        if not self.comments:
            return "# Comments Trail\n\n（暂无注释）\n"

        # 按任务分组
        tasks: dict[str, list[Comment]] = {}
        for c in self.comments:
            tasks.setdefault(c.task_id, []).append(c)

        pending_count = len(self.pending())
        lines = [
            "# Comments Trail",
            "",
            f"共 {len(self.comments)} 条注释"
            + (f"（其中 {pending_count} 条待确认）" if pending_count else ""),
            "",
        ]

        for task_id in sorted(tasks.keys()):
            comments = sorted(tasks[task_id], key=lambda c: c.timestamp)
            lines.append(f"## Task: {task_id}")
            lines.append("")
            for c in comments:
                icon = _TYPE_ICONS.get(c.type, "•")
                status = "✅" if c.resolved else "⏳"
                lines.append(
                    f"- [{c.timestamp}] {icon} **{c.type.value}** {status} "
                    f"(confidence={c.confidence:.2f}, author={c.author})"
                )
                # 内容缩进显示
                for line in c.content.splitlines() or [""]:
                    lines.append(f"  > {line}")
            lines.append("")

        return "\n".join(lines)

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(
            [c.model_dump(mode="json") for c in self.comments],
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "CommentTrail":
        """从 JSON 字符串反序列化。"""
        trail = cls()
        data = json.loads(json_str)
        for item in data:
            trail.comments.append(Comment.model_validate(item))
        return trail

    # ------------------------------------------------------------------ #
    # 便捷
    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self.comments)

    def __repr__(self) -> str:
        return f"<CommentTrail comments={len(self.comments)} pending={len(self.pending())}>"
