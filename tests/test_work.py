"""Work 模式测试。

覆盖 Comments / Corrector / TaskQueue / Orchestrator / 模板。
所有测试独立运行，不依赖外部服务或凭证。
"""

from __future__ import annotations

from typing import Any

import pytest

from loopkits.core.workflow import Step, WorkFlow
from loopkits.work.comments import CommentTrail, CommentType
from loopkits.work.corrector import ActionType, WorkCorrector
from loopkits.work.orchestrator import WorkOrchestrator
from loopkits.work.queue import Task, TaskQueue, TaskStatus
from loopkits.work.templates import (
    email_triage_template,
    schedule_organize_template,
    weekly_report_template,
)


# ====================================================================== #
# Comments
# ====================================================================== #
def test_comments_add_and_query():
    """Comments 添加与查询。"""
    trail = CommentTrail()
    assert len(trail) == 0

    # 添加注释
    c1 = trail.add(CommentType.DECISION, "分类为高优先级", task_id="t1", confidence=0.9)
    c2 = trail.add(CommentType.EVIDENCE, "包含紧急关键词", task_id="t1", confidence=0.85)
    c3 = trail.add(CommentType.QUESTION, "无法确定优先级", task_id="t2", confidence=0.4)

    assert len(trail) == 3
    assert c1.type == CommentType.DECISION
    assert c1.task_id == "t1"

    # 按任务查询
    t1_comments = trail.for_task("t1")
    assert len(t1_comments) == 2
    t2_comments = trail.for_task("t2")
    assert len(t2_comments) == 1

    # 待确认列表
    pending = trail.pending()
    assert len(pending) == 1  # 只有 c3 是 QUESTION 未解决
    assert pending[0].task_id == "t2"

    # 解决
    resolved = trail.resolve_for_task("t2")
    assert resolved == 1
    assert len(trail.pending()) == 0


def test_comments_markdown():
    """Comments to_markdown 生成可读文本。"""
    trail = CommentTrail()
    # 空轨迹
    md = trail.to_markdown()
    assert "Comments" in md or "暂无" in md

    # 有注释
    trail.add(CommentType.DECISION, "将邮件分类为高优先级", task_id="t1", confidence=0.9)
    trail.add(CommentType.NEXT_STEP, "建议人工审核", task_id="t1")
    md = trail.to_markdown()
    assert "t1" in md
    assert "DECISION" in md
    assert "将邮件分类为高优先级" in md
    assert "NEXT_STEP" in md


# ====================================================================== #
# Corrector
# ====================================================================== #
def test_corrector_pause_low_confidence():
    """低置信度触发 PAUSE。"""
    corrector = WorkCorrector(confidence_threshold=0.7)
    action = corrector.check(
        task="t1",
        result={"ok": True, "status": "success"},
        confidence=0.5,
    )
    assert action.type == ActionType.PAUSE
    assert "置信度" in action.reason
    assert "0.50" in action.reason
    assert action.question  # 非空提问
    assert action.next_step  # 非空下一步建议


def test_corrector_proceed_high_confidence():
    """高置信度 PROCEED。"""
    corrector = WorkCorrector(confidence_threshold=0.7)
    action = corrector.check(
        task="t1",
        result={"ok": True, "status": "success"},
        confidence=0.95,
    )
    assert action.type == ActionType.PROCEED
    assert "充足" in action.reason or "符合规范" in action.reason
    assert action.question == ""
    assert action.next_step == ""


def test_corrector_correct_on_deviation():
    """结果偏离规范触发 CORRECT。"""
    corrector = WorkCorrector(confidence_threshold=0.7)
    action = corrector.check(
        task="t1",
        result={"ok": False, "error": "执行失败"},
        confidence=0.9,  # 置信度足够，但结果偏离
    )
    assert action.type == ActionType.CORRECT
    assert len(action.suggestions) > 0


# ====================================================================== #
# TaskQueue
# ====================================================================== #
def test_queue_single_pause_not_block():
    """单任务暂停不阻塞其他任务。"""
    q = TaskQueue()
    q.add(Task(id="t1", name="任务1"))
    q.add(Task(id="t2", name="任务2"))
    q.add(Task(id="t3", name="任务3"))

    # 取 t1 并暂停
    t1 = q.next()
    assert t1.id == "t1"
    q.mark_running(t1.id)
    q.mark_paused(t1.id, reason="置信度不足")

    assert q.paused_count() == 1

    # t2 不受影响
    t2 = q.next()
    assert t2.id == "t2"
    q.mark_running(t2.id)
    q.mark_done(t2.id, result={"ok": True}, confidence=0.95)

    # t3 不受影响
    t3 = q.next()
    assert t3.id == "t3"

    assert q.done_count() == 1
    assert q.pending_count() == 1  # t3 仍 pending
    assert q.paused_count() == 1

    # 恢复 t1
    assert q.resume("t1") is True
    assert q.pending_count() == 2  # t1 和 t3


def test_queue_mark_failed():
    """任务标记失败。"""
    q = TaskQueue()
    q.add(Task(id="t1", name="任务1"))
    t = q.next()
    q.mark_running(t.id)
    q.mark_failed(t.id, error="执行异常")
    assert q.failed_count() == 1
    assert q.get("t1").error == "执行异常"


# ====================================================================== #
# Orchestrator
# ====================================================================== #
def test_orchestrator_batch():
    """批次执行：多个任务通过 WorkFlow 执行。"""
    # 构建简单 WorkFlow
    def step_action(ctx: dict[str, Any]) -> dict[str, Any]:
        ctx["confidence"] = 0.9
        return {"result": "ok", "task_id": ctx.get("task_id")}

    wf = WorkFlow(
        name="test-wf",
        steps=[Step("process", step_action, outputs="processed")],
    )

    from loopkits.work.orchestrator import WorkConfig

    config = WorkConfig(
        name="batch-test",
        description="批次测试",
        workflow=wf,
        corrector=WorkCorrector(confidence_threshold=0.7),
    )
    orch = WorkOrchestrator(config)

    tasks = [
        Task(id="t1", name="任务1"),
        Task(id="t2", name="任务2"),
        Task(id="t3", name="任务3"),
    ]
    batch_result = orch.run_batch(tasks)

    assert batch_result.total == 3
    assert batch_result.done == 3
    assert batch_result.paused == 0
    assert batch_result.failed == 0
    assert len(batch_result.task_results) == 3
    # 每个任务都成功
    for tr in batch_result.task_results:
        assert tr.success is True
        assert tr.action_type == ActionType.PROCEED.value


def test_orchestrator_paused_tasks():
    """获取暂停任务：低置信度任务被暂停，可通过 paused_tasks() 获取。"""
    # 构建低置信度 WorkFlow
    def low_conf_step(ctx: dict[str, Any]) -> dict[str, Any]:
        ctx["confidence"] = 0.4  # 低于阈值
        return {"result": "uncertain"}

    wf = WorkFlow(
        name="low-conf-wf",
        steps=[Step("process", low_conf_step, outputs="processed")],
    )

    from loopkits.work.orchestrator import WorkConfig

    config = WorkConfig(
        name="pause-test",
        description="暂停测试",
        workflow=wf,
        corrector=WorkCorrector(confidence_threshold=0.7),
    )
    orch = WorkOrchestrator(config)

    tasks = [Task(id="t1", name="低置信度任务")]
    batch_result = orch.run_batch(tasks)

    assert batch_result.total == 1
    assert batch_result.paused == 1
    assert batch_result.done == 0

    # 通过 paused_tasks() 获取
    paused = orch.paused_tasks()
    assert len(paused) == 1
    assert paused[0].id == "t1"
    assert paused[0].status == TaskStatus.PAUSED

    # 通过 resume() 恢复
    resume_result = orch.resume("t1", decision="proceed")
    assert resume_result.success is True
    assert resume_result.action_type == ActionType.PROCEED.value


def test_orchestrator_resume_cancel():
    """人工取消暂停任务。"""
    def low_conf_step(ctx: dict[str, Any]) -> dict[str, Any]:
        ctx["confidence"] = 0.4
        return {"result": "uncertain"}

    wf = WorkFlow(name="cancel-wf", steps=[Step("process", low_conf_step)])
    from loopkits.work.orchestrator import WorkConfig

    config = WorkConfig(
        name="cancel-test",
        workflow=wf,
        corrector=WorkCorrector(confidence_threshold=0.7),
    )
    orch = WorkOrchestrator(config)
    orch.run_batch([Task(id="t1", name="取消测试")])

    result = orch.resume("t1", decision="cancel")
    assert result.success is False
    assert result.action_type == "CANCELLED"


# ====================================================================== #
# 模板
# ====================================================================== #
def test_template_weekly_report():
    """周报模板构建：WorkFlow 可执行，无凭证时使用 mock 数据。"""
    config = weekly_report_template()
    assert config.name == "每周项目周报"
    assert config.pattern_name == "changelog-drafter"
    assert len(config.workflow.steps) == 4
    assert "github" in config.required_services
    assert "email" in config.required_services
    assert config.schedule == "0 9 * * 1"

    # 无凭证执行（使用 mock 数据）
    result = config.workflow.execute({"services": {}})
    assert result.success is True
    assert result.context.get("commits") is not None
    assert len(result.context["commits"]) > 0
    assert result.context.get("changelog") is not None
    assert result.context.get("report") is not None
    assert "项目周报" in result.context["report"]


def test_template_email_triage():
    """邮件分类模板构建与执行。"""
    config = email_triage_template()
    assert config.name == "邮件分类"
    assert len(config.workflow.steps) == 4

    result = config.workflow.execute({"services": {}})
    assert result.success is True
    assert len(result.context["emails"]) > 0
    assert "classified" in result.context
    assert "actions" in result.context


def test_template_schedule_organize():
    """日程整理模板构建与执行。"""
    config = schedule_organize_template()
    assert config.name == "日程整理"
    assert len(config.workflow.steps) == 3

    result = config.workflow.execute({"services": {}})
    assert result.success is True
    assert len(result.context["events"]) > 0
    assert "conflicts" in result.context
    assert "suggestions" in result.context
