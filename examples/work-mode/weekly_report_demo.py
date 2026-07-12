#!/usr/bin/env python3
"""Weekly Report 演示 — 用 LoopFlow Work 模式生成项目周报。

本示例展示如何用 LoopFlow 的 Work 模式 API 批量生成周报。

- 使用 weekly_report_template() 模板
- 通过 WorkOrchestrator 批量执行多个周报任务
- 打印 Comments 轨迹（决策、依据、信息）
- 用 mock 数据（无需任何凭证）

运行方式::

    python examples/work-mode/weekly_report_demo.py

无需安装 GitHub/邮件凭证 — 模板内置 mock 数据，dry_run 自动回退。
"""

from __future__ import annotations

from loopflow.work.orchestrator import WorkOrchestrator
from loopflow.work.queue import Task
from loopflow.work.templates import weekly_report_template


def main() -> None:
    """演示 Work 模式周报生成的批量执行流程。"""
    print("=" * 70)
    print("LoopFlow Work 模式示例 — Weekly Report（项目周报生成）")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # 步骤 1：加载周报模板
    # ------------------------------------------------------------------ #
    # weekly_report_template() 返回一个 WorkConfig，包含：
    # - 预构建的 WorkFlow（4 个 Step：fetch-commits → draft-changelog →
    #   render-report → send-email）
    # - 所需服务声明（github / email）
    # - Corrector（置信度阈值 0.7）
    # - 调度（每周一 9:00）
    print("\n[1] 加载 weekly_report_template 模板...")
    config = weekly_report_template()
    print(f"    名称：{config.name}")
    print(f"    描述：{config.description}")
    print(f"    复用模式：{config.pattern_name}")
    print(f"    所需服务：{config.required_services}")
    print(f"    调度：{config.schedule}")
    print(f"    Corrector 阈值：{config.corrector.confidence_threshold}")
    print(f"    WorkFlow 步骤：{[s.name for s in config.workflow.steps]}")

    # ------------------------------------------------------------------ #
    # 步骤 2：构造 WorkOrchestrator
    # ------------------------------------------------------------------ #
    # WorkOrchestrator 封装 Code 循环 + WorkFlow + 服务。
    # 不注入 services 字典 → 所有 Step 回退到 mock 数据（dry_run）。
    print("\n[2] 构造 WorkOrchestrator（不注入服务，使用 mock 数据）...")
    orch = WorkOrchestrator(config)
    print(f"    {orch!r}")

    # ------------------------------------------------------------------ #
    # 步骤 3：构造批量任务
    # ------------------------------------------------------------------ #
    # 模拟为两个项目生成周报。每个 Task 有独立 id / name / payload。
    # payload 可包含项目特定信息（此处简化为空 dict，模板会用 mock 数据）。
    print("\n[3] 构造批量任务（2 个项目的周报）...")
    tasks = [
        Task(
            id="weekly-proj-alpha",
            name="项目 Alpha 周报",
            payload={"project": "alpha", "week": "2026-W28"},
        ),
        Task(
            id="weekly-proj-beta",
            name="项目 Beta 周报",
            payload={"project": "beta", "week": "2026-W28"},
        ),
    ]
    for t in tasks:
        print(f"    + Task({t.id!r}, {t.name!r})")

    # ------------------------------------------------------------------ #
    # 步骤 4：批量执行
    # ------------------------------------------------------------------ #
    # run_batch() 会：
    # 1. 入队所有任务
    # 2. 逐个执行 WorkFlow（4 个 Step 串联）
    # 3. 每个 Step 完成后记录 DECISION + EVIDENCE 注释
    # 4. 用 Corrector 检查置信度
    # 5. 置信度 >= 0.7 → PROCEED（标记 DONE）
    #    置信度 <  0.7 → PAUSE（标记 PAUSED，记录 QUESTION + NEXT_STEP）
    print("\n[4] 批量执行（run_batch）...")
    batch = orch.run_batch(tasks)

    # ------------------------------------------------------------------ #
    # 步骤 5：打印批量结果
    # ------------------------------------------------------------------ #
    print(f"\n[5] 批量执行结果：")
    print(f"    总数：{batch.total}")
    print(f"    已完成：{batch.done}")
    print(f"    已暂停：{batch.paused}")
    print(f"    已失败：{batch.failed}")

    print("\n    --- 各任务结果 ---")
    for tr in batch.task_results:
        print(f"    • {tr.task_id}")
        print(f"      success={tr.success}, confidence={tr.confidence:.2f}, action={tr.action_type}")

    # ------------------------------------------------------------------ #
    # 步骤 6：打印 Comments 轨迹
    # ------------------------------------------------------------------ #
    # Comments 是 Work 模式的核心审计机制：每个决策都有依据，
    # 每个暂停都有提问和下一步建议。
    print(f"\n[6] Comments 轨迹（共 {len(batch.comments)} 条）：")
    for c in batch.comments:
        print(f"    [{c.timestamp}] {c.type.value} (task={c.task_id}, conf={c.confidence:.2f})")
        # 内容缩进显示
        for line in c.content.splitlines():
            print(f"      > {line}")

    # ------------------------------------------------------------------ #
    # 步骤 7：提取生成的周报内容
    # ------------------------------------------------------------------ #
    print("\n[7] 提取生成的周报内容（第一个任务）：")
    print("-" * 70)
    first_result = batch.task_results[0]
    if isinstance(first_result.result, dict) and "report" in first_result.result:
        print(first_result.result["report"])
    else:
        print("(未找到 report 字段)")
    print("-" * 70)

    # ------------------------------------------------------------------ #
    # 步骤 8：打印完整 Work 模式报告
    # ------------------------------------------------------------------ #
    print("\n[8] 完整 Work 模式报告（to_report）：")
    print("-" * 70)
    print(orch.to_report())
    print("-" * 70)

    print("\n✓ Weekly Report 演示完成。")
    print("  实际使用时，注入 GitHub 与邮件服务即可处理真实项目：")
    print("    from loopflow.services import GitHubService, EmailService")
    print('    config.services = {"github": GitHubService(token=...),')
    print('                        "email": EmailService(...)}')


if __name__ == "__main__":
    main()
