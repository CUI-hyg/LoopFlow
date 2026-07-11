#!/usr/bin/env python3
"""Email Triage 演示 — 用 LoopKits Work 模式分类邮件。

本示例展示 Work 模式的 Corrector 机制：低置信度时暂停任务而非盲目执行。

- 使用 email_triage_template() 模板
- 第一批：默认阈值（0.7）→ 置信度充足 → PROCEED
- 第二批：提高阈值（0.95）→ 置信度不足 → PAUSE，生成提问与下一步建议
- 打印暂停任务与 Corrector 提问
- 用 mock 数据（无需任何凭证）

运行方式::

    python examples/work-mode/email_triage_demo.py

无需安装邮件凭证 — 模板内置 mock 邮件数据，dry_run 自动回退。
"""

from __future__ import annotations

from loopkits.work.orchestrator import WorkOrchestrator
from loopkits.work.queue import Task
from loopkits.work.corrector import WorkCorrector
from loopkits.work.templates import email_triage_template


def main() -> None:
    """演示 Work 模式邮件分类与 Corrector 暂停机制。"""
    print("=" * 70)
    print("LoopKits Work 模式示例 — Email Triage（邮件分类）")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # 步骤 1：加载邮件分类模板
    # ------------------------------------------------------------------ #
    # email_triage_template() 返回一个 WorkConfig，包含：
    # - 预构建的 WorkFlow（4 个 Step：read-unread → classify-priority →
    #   review-classification → mark-reply）
    # - Corrector（默认置信度阈值 0.7）
    # - 调度（每日 9:00）
    # mock 邮件含 4 封：1 封紧急（high）、1 封周报（low）、1 封讨论（medium）、
    # 1 封订阅（low）。review 步骤根据 medium 占比计算置信度。
    print("\n[1] 加载 email_triage_template 模板...")
    config = email_triage_template()
    print(f"    名称：{config.name}")
    print(f"    描述：{config.description}")
    print(f"    所需服务：{config.required_services}")
    print(f"    调度：{config.schedule}")
    print(f"    Corrector 阈值：{config.corrector.confidence_threshold}")
    print(f"    WorkFlow 步骤：{[s.name for s in config.workflow.steps]}")

    # ------------------------------------------------------------------ #
    # 步骤 2：第一批 — 默认阈值（0.7），置信度充足 → PROCEED
    # ------------------------------------------------------------------ #
    # mock 数据下，medium_ratio = 1/4 = 0.25 ≤ 0.3 → confidence = 0.9
    # 0.9 >= 0.7（阈值）→ Corrector 返回 PROCEED，任务标记为 DONE。
    print("\n[2] 第一批：默认阈值 0.7（置信度 0.9 充足 → PROCEED）...")
    orch1 = WorkOrchestrator(config)
    tasks1 = [
        Task(id="email-batch-1", name="晨间邮件分类", payload={"slot": "morning"}),
    ]
    batch1 = orch1.run_batch(tasks1)

    print(f"    总数：{batch1.total}，完成：{batch1.done}，暂停：{batch1.paused}")
    for tr in batch1.task_results:
        print(f"    • {tr.task_id}: action={tr.action_type}, confidence={tr.confidence:.2f}")

    # 提取分类结果
    if batch1.task_results and isinstance(batch1.task_results[0].result, dict):
        classified = batch1.task_results[0].result.get("classified", {})
        print(f"\n    分类结果：high={len(classified.get('high', []))}, "
              f"medium={len(classified.get('medium', []))}, "
              f"low={len(classified.get('low', []))}")
        for email_item in classified.get("high", []):
            print(f"    [HIGH] {email_item.get('subject')} — {email_item.get('reason')}")
        for email_item in classified.get("low", []):
            print(f"    [LOW]  {email_item.get('subject')} — {email_item.get('reason')}")

    # ------------------------------------------------------------------ #
    # 步骤 3：第二批 — 提高阈值（0.95），置信度不足 → PAUSE
    # ------------------------------------------------------------------ #
    # 将 Corrector 阈值提高到 0.95，使原本 0.9 的置信度变为「不足」。
    # Corrector.check() 发现 confidence(0.9) < threshold(0.95) → 返回 PAUSE，
    # 生成 QUESTION（提问）+ NEXT_STEP（下一步建议）+ PENDING（待确认）注释。
    # 任务被标记为 PAUSED，但不阻塞队列中的其他任务。
    print("\n[3] 第二批：提高阈值至 0.95（置信度 0.9 不足 → PAUSE）...")
    config_strict = config.model_copy(deep=True)
    config_strict.corrector = WorkCorrector(confidence_threshold=0.95)
    print(f"    新阈值：{config_strict.corrector.confidence_threshold}")

    orch2 = WorkOrchestrator(config_strict)
    tasks2 = [
        Task(id="email-batch-2a", name="午间邮件分类", payload={"slot": "noon"}),
        Task(id="email-batch-2b", name="晚间邮件分类", payload={"slot": "evening"}),
    ]
    batch2 = orch2.run_batch(tasks2)

    print(f"\n    总数：{batch2.total}，完成：{batch2.done}，暂停：{batch2.paused}")
    for tr in batch2.task_results:
        print(f"    • {tr.task_id}: action={tr.action_type}, confidence={tr.confidence:.2f}, paused={tr.paused}")

    # ------------------------------------------------------------------ #
    # 步骤 4：打印暂停任务与 Corrector 提问
    # ------------------------------------------------------------------ #
    paused_tasks = orch2.paused_tasks()
    print(f"\n[4] 暂停任务（共 {len(paused_tasks)} 个，等待人工确认）：")
    for t in paused_tasks:
        print(f"    ⏸️ Task({t.id!r}, {t.name!r})")
        print(f"       暂停原因：{t.paused_reason}")

    # 打印暂停任务的 QUESTION 与 NEXT_STEP 注释
    print("\n    --- Corrector 提问与下一步建议 ---")
    for c in batch2.comments:
        if c.type.value in ("QUESTION", "NEXT_STEP", "PENDING"):
            print(f"    [{c.type.value}] task={c.task_id}")
            for line in c.content.splitlines():
                print(f"      > {line}")

    # ------------------------------------------------------------------ #
    # 步骤 5：演示人工恢复暂停任务
    # ------------------------------------------------------------------ #
    # resume() 方法根据人工决策恢复暂停的任务：
    # - "proceed" → 标记为 DONE
    # - "cancel" → 标记为 FAILED
    # - {"action": "correct", "result": {...}} → 带修正结果继续
    if paused_tasks:
        print(f"\n[5] 人工恢复暂停任务（演示 resume）...")
        first_paused = paused_tasks[0]
        print(f"    恢复任务：{first_paused.id}")
        resume_result = orch2.resume(first_paused.id, "proceed")
        print(f"    恢复结果：success={resume_result.success}, action={resume_result.action_type}")

        # 恢复后的队列状态
        print(f"\n    恢复后队列状态：")
        print(f"    完成：{orch2.queue.done_count()}，暂停：{orch2.queue.paused_count()}")

    # ------------------------------------------------------------------ #
    # 步骤 6：打印完整 Comments 轨迹
    # ------------------------------------------------------------------ #
    print(f"\n[6] 完整 Comments 轨迹（第二批，共 {len(batch2.comments)} 条）：")
    print("-" * 70)
    print(orch2.comments.to_markdown())
    print("-" * 70)

    print("\n✓ Email Triage 演示完成。")
    print("  Corrector 机制核心：低置信度时暂停（PAUSE）而非盲目执行，")
    print("  生成提问与下一步建议，等待人工 resume() 恢复。")


if __name__ == "__main__":
    main()
