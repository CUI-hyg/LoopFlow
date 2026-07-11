#!/usr/bin/env python3
"""Daily Triage 演示 — 用 LoopKits 运行 daily-triage 模式。

本示例展示如何用 LoopKits 的 Code 模式 API 运行「每日分诊」循环模式。

- 使用 dry_run 模式（无需任何外部凭证）
- 通过模式注册表获取 DailyTriage 类
- 打印分类结果（P0/P1/P2/P3 分布、需人介入项、Watch List）

运行方式::

    python examples/code-mode/daily_triage_demo.py

无需安装 GitHub Token 或任何服务凭证 — dry_run 会自动回退到内置 mock 数据。
"""

from __future__ import annotations

from loopkits.patterns.registry import get, list_patterns


def main() -> None:
    """演示 daily-triage 模式的 dry_run 流程。"""
    print("=" * 70)
    print("LoopKits Code 模式示例 — Daily Triage（每日分诊）")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # 步骤 1：列出所有可用模式，确认 daily-triage 存在
    # ------------------------------------------------------------------ #
    print("\n[1] 已注册的循环模式：")
    for meta in list_patterns():
        print(
            f"    - {meta.name:<22} | L:{meta.default_level.value} | "
            f"cadence={meta.cadence or '-':<4} | {meta.description}"
        )

    # ------------------------------------------------------------------ #
    # 步骤 2：从注册表获取 DailyTriage 模式类
    # ------------------------------------------------------------------ #
    pattern_cls = get("daily-triage")
    if pattern_cls is None:
        raise RuntimeError("模式 daily-triage 未注册")

    # 实例化模式（不注入任何 service_provider，dry_run 会强制走 mock 路径）
    pattern = pattern_cls()
    print(f"\n[2] 已加载模式：{pattern!r}")
    print(f"    元信息：name={pattern.meta.name!r}")
    print(f"    描述：{pattern.meta.description}")
    print(f"    节奏：{pattern.meta.cadence}（每日运行）")
    print(f"    默认级别：{pattern.effective_level.value}（仅报告，不自动修改）")

    # ------------------------------------------------------------------ #
    # 步骤 3：dry_run — 无凭证模拟运行
    # ------------------------------------------------------------------ #
    # dry_run() 会将 _force_mock 置为 True，使 _service() 始终返回 None，
    # 子类的 _execute 会回退到内置 _MOCK_ITEMS 数据。
    print("\n[3] 执行 dry_run（无凭证模拟运行）...")
    result = pattern.dry_run()

    # ------------------------------------------------------------------ #
    # 步骤 4：打印分类结果
    # ------------------------------------------------------------------ #
    print("\n[4] 分类结果：")
    print(f"    扫描总数：{result['scanned']} 项 Issue/PR")
    print(f"    按优先级分布：{result['by_priority']}")

    print("\n    --- High Priority（可尝试 L2 修复）---")
    for item in result["high_priority"]:
        print(
            f"    [{item['priority']}] #{item['id']} {item['title']} "
            f"({item['scope']}/{item['kind']})"
        )

    print("\n    --- Needs Human（需人介入：P0/P1/security）---")
    for item in result["needs_human"]:
        print(
            f"    [{item['priority']}] #{item['id']} {item['title']} "
            f"labels={item['labels']}"
        )

    print("\n    --- Watch List（监控项）---")
    for item in result["watch_list"]:
        print(f"    [{item['priority']}] #{item['id']} {item['title']}")

    # ------------------------------------------------------------------ #
    # 步骤 5：展示 L1 级别的限制（无修复尝试）
    # ------------------------------------------------------------------ #
    print(f"\n[5] L1 级别行为：fixes={result['fixes']}（L1 仅报告，不自动修复）")
    print("    如需自动修复单文件 bugfix，请用 L2 级别（需注入 git 服务）。")

    # ------------------------------------------------------------------ #
    # 步骤 6：打印完整人可读报告
    # ------------------------------------------------------------------ #
    print("\n[6] 完整分诊报告：")
    print("-" * 70)
    print(result["report"])
    print("-" * 70)

    print("\n✓ Daily Triage 演示完成。")
    print("  实际使用时，注入 GitHubService 即可扫描真实 Issue/PR：")
    print("    from loopkits.services import GitHubService")
    print('    svc = GitHubService(token="ghp_xxx")')
    print('    pattern = DailyTriage(service_provider={"github": svc})')


if __name__ == "__main__":
    main()
