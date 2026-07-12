#!/usr/bin/env python3
"""CI Sweeper 演示 — 用 LoopKits 运行 ci-sweeper 模式。

本示例展示如何用 LoopKits 的 Code 模式 API 运行「CI 失败清扫」循环模式。

- 使用 dry_run 模式（无需任何外部凭证）
- 展示 L1（仅报告根因分析）与 L2（尝试 worktree 修复）的级别差异
- 打印 CI 失败分类（test-regression / lint / security / infrastructure）

运行方式::

    python examples/code-mode/ci_sweeper_demo.py

无需安装任何 CI 服务凭证 — dry_run 会自动回退到内置 mock 数据。
"""

from __future__ import annotations

from loopkits.core.loop import TrustLevel
from loopkits.patterns.registry import get


def main() -> None:
    """演示 ci-sweeper 模式的 dry_run 流程，并对比 L1/L2 级别差异。"""
    print("=" * 70)
    print("LoopKits Code 模式示例 — CI Sweeper（CI 失败清扫）")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # 步骤 1：获取 CISweeper 模式类
    # ------------------------------------------------------------------ #
    pattern_cls = get("ci-sweeper")
    if pattern_cls is None:
        raise RuntimeError("模式 ci-sweeper 未注册")

    print(f"\n[1] 已加载模式：ci-sweeper")
    print(f"    描述：扫描 CI 失败 → 分类 → 定位根因 → （L2）worktree 修复")
    print(f"    节奏：15m（CI 失败后 15 分钟内响应）")
    print(f"    标签：ci / failures / diagnostics / fix")

    # ------------------------------------------------------------------ #
    # 步骤 2：L1 级别 dry_run — 仅报告根因分析，不自动修复
    # ------------------------------------------------------------------ #
    # L1（仅报告）：分析失败日志、分类、定位根因，但不在 worktree 中修复。
    # infrastructure / security 失败必须升级给人，不自动修复。
    print("\n[2] L1 级别 dry_run（仅报告根因分析）...")
    pattern_l1 = pattern_cls(level=TrustLevel.L1)
    result_l1 = pattern_l1.dry_run()

    print(f"\n    分析失败数：{result_l1['failures_analyzed']}")
    print(f"    修复尝试：{len(result_l1['fixes'])}（L1 不自动修复）")
    print(f"    升级给人：{len(result_l1['escalations'])} 项（infra/security）")

    print("\n    --- 失败根因分析明细 ---")
    for a in result_l1["analyses"]:
        rc = a["root_cause"]
        print(f"    • run #{a['run_id']}（{a['branch']}）[{a['category']}]")
        print(f"      标题：{a['title']}")
        print(f"      根因：{rc['file']}:{rc['line']} — {rc['error_message'][:80]}")
        if a["fix_hint"]:
            print(f"      提示：{a['fix_hint']}")
        print(f"      可修复：{a['fixable']}")

    print("\n    --- 升级项（基础设施/安全，不自动修复）---")
    for e in result_l1["escalations"]:
        print(f"    • run #{e['run_id']} [{e['category']}] {e['title']}")

    # ------------------------------------------------------------------ #
    # 步骤 3：L2 级别 dry_run — 对可修复项尝试 worktree 修复
    # ------------------------------------------------------------------ #
    # L2（辅助修复）：对 test-regression / dependency / lint 类失败，
    # 在隔离 worktree 中提交修复，verifier 验证后才能合并。
    # 仍升级 infrastructure / security 给人。
    print("\n[3] L2 级别 dry_run（对可修复项尝试 worktree 修复）...")
    pattern_l2 = pattern_cls(level=TrustLevel.L2)
    result_l2 = pattern_l2.dry_run()

    print(f"\n    分析失败数：{result_l2['failures_analyzed']}")
    print(f"    修复尝试：{len(result_l2['fixes'])}（L2 会尝试修复）")
    print(f"    升级给人：{len(result_l2['escalations'])} 项（infra/security 仍升级）")

    print("\n    --- L2 修复尝试明细 ---")
    for fix in result_l2["fixes"]:
        print(f"    • run #{fix['run_id']} [{fix['category']}]")
        print(f"      文件：{fix['file']}")
        print(f"      worktree：{fix['worktree']}")
        print(f"      状态：{fix['status']} (verifier={fix['verifier']}, attempts={fix['attempts']})")

    # ------------------------------------------------------------------ #
    # 步骤 4：L1 vs L2 对比
    # ------------------------------------------------------------------ #
    print("\n[4] L1 vs L2 级别差异对比：")
    print(f"    {'指标':<20} {'L1（仅报告）':<20} {'L2（辅助修复）':<20}")
    print(f"    {'-' * 60}")
    print(f"    {'分析失败数':<18} {result_l1['failures_analyzed']:<20} {result_l2['failures_analyzed']:<20}")
    print(f"    {'修复尝试':<18} {len(result_l1['fixes']):<20} {len(result_l2['fixes']):<20}")
    print(f"    {'升级给人':<18} {len(result_l1['escalations']):<20} {len(result_l2['escalations']):<20}")

    print("\n    关键差异：")
    print("    - L1：只分析根因、生成报告，不触碰代码")
    print("    - L2：对 test-regression/lint/dependency 在 worktree 中修复")
    print("    - 两者都会升级 infrastructure/security 失败给人（不自动修复）")

    # ------------------------------------------------------------------ #
    # 步骤 5：打印完整 L2 报告
    # ------------------------------------------------------------------ #
    print("\n[5] 完整 CI Sweeper 报告（L2）：")
    print("-" * 70)
    print(result_l2["report"])
    print("-" * 70)

    print("\n✓ CI Sweeper 演示完成。")
    print("  实际使用时，注入 CI 与 git 服务即可处理真实失败：")
    print("    from loopkits.services import GitHubService")
    print('    ci = GitHubService(token="ghp_xxx")  # 复用为 CI 服务')
    print('    pattern = CISweeper(service_provider={"ci": ci, "git": ci}, level=TrustLevel.L2)')


if __name__ == "__main__":
    main()
