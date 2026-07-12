# Code 模式示例

LoopFlow 的 **Code 模式**面向开发者，提供 7 个可复用的 Loop Engineering 循环模式。
每个模式都是 `Pattern` 子类，通过 `service_provider` 抽象外部服务依赖，
支持 `dry_run()` 无凭证模拟运行。

## 7 个循环模式

| 模式 | 节奏 | 默认级别 | 用途 | 触发场景 |
|------|------|----------|------|----------|
| `daily-triage` | `1d` | L1 | 每日扫描 Issue/PR，按 P0/P1/P2/P3 分类 | 每日工作日开始 |
| `pr-babysitter` | `5m` | L1 | 新 PR 审查：代码风格、测试覆盖、安全 | PR 提交/更新时 |
| `ci-sweeper` | `15m` | L1 | CI 失败分析：分类根因、定位文件、尝试修复 | CI 失败事件 |
| `dependency-sweeper` | `6h` | L1 | 依赖升级：patch 自动 / minor+major 评估 | 定期扫描 |
| `changelog-drafter` | `1d` | L1 | 基于 git log 生成 RELEASE_NOTES_DRAFT.md | 每日或发布前 |
| `post-merge-cleanup` | `1d` | L1 | 合并后清理分支、更新 Issue、标记关闭 | PR 合并后 |
| `issue-triage` | `2h` | L1 | 新 Issue 分析、建议标签、判断优先级 | 新 Issue 创建时 |

## 信任级别（L1/L2/L3）

- **L1（仅报告）** — 默认级别。扫描、分析、生成报告，不修改任何代码或 Issue。
- **L2（辅助修复）** — 在隔离 worktree 中提交修复，verifier 验证后方可合并。
  infrastructure / security / auth / payments 失败仍升级给人。
- **L3（全自动）** — 全自动执行，需严格约束与 verifier 门控。慎用。

## 示例文件

| 文件 | 说明 |
|------|------|
| `daily_triage_demo.py` | Daily Triage 演示：扫描 Issue/PR、分类、生成报告 |
| `ci_sweeper_demo.py` | CI Sweeper 演示：分析 CI 失败、对比 L1/L2 级别差异 |

## 运行示例

所有示例均使用 `dry_run` 模式，无需任何外部凭证（GitHub Token、CI Token 等）。

```bash
# Daily Triage 演示
python examples/code-mode/daily_triage_demo.py

# CI Sweeper 演示（含 L1/L2 对比）
python examples/code-mode/ci_sweeper_demo.py
```

## 核心 API

```python
from loopflow.patterns.registry import get, list_patterns
from loopflow.core.loop import TrustLevel

# 列出所有模式元数据
for meta in list_patterns():
    print(meta.name, meta.description)

# 按名获取模式类
DailyTriage = get("daily-triage")

# 实例化（无凭证 → dry_run）
pattern = DailyTriage()

# 指定 L2 级别
pattern_l2 = DailyTriage(level=TrustLevel.L2)

# dry_run（无需凭证）
result = pattern.dry_run()
print(result["report"])

# 真实运行（注入服务）
from loopflow.services import GitHubService
svc = GitHubService(token="ghp_xxx")
pattern = DailyTriage(service_provider={"github": svc})
loop = pattern.build_loop()
loop_result = loop.run()
```

## 多循环协调

运行多个循环时，推荐优先级：

```
CI Sweeper → PR Babysitter → Dependency Sweeper → Post-Merge / Changelog Drafter（闲时）→ Daily Triage（报告）
```

详见 `references/loop-engineering/docs/multi-loop.md`。
