# LoopKits

> **LoopFlow = Loops × WorkFlows + Agents & Services**

LoopKits 是一个 Python 原生的 **Loop Engineering** 框架，将自治循环（Loops）、
工作流（WorkFlows）、智能体（Agents）与服务连接器（Services）整合为统一的
编程模型，让 AI 驱动的开发与办公自动化可组合、可审计、可信任。

## 核心特性

- **双模式**：Code 模式（7 个开发循环模式）+ Work 模式（办公任务模板 + Comments 轨迹）
- **三形态**：Python 库 / CLI 工具 / Skill 文档，同一套循环逻辑三种分发方式
- **三级信任**：L1 仅报告 / L2 辅助修复（worktree + verifier）/ L3 全自动（严格约束门控）
- **安全门控**：路径保护（denylist）、预算追踪、kill switch、Constraints 约束文件
- **无凭证可运行**：所有模式与模板支持 `dry_run`，内置 mock 数据，零凭证即可体验

## 快速开始

```bash
# 安装（开发模式）
pip install -e .

# 初始化脚手架（生成 LOOP.md / STATE.md / loop-budget.yaml / loop-constraints.md）
loopflow init                           # 当前目录，默认 daily-triage / L1
loopflow init /tmp/proj --pattern ci-sweeper --tool claude --level L2

# 运行循环模式
loopflow run daily-triage --dry-run     # 模拟运行（无需凭证）
loopflow run daily-triage --level L2    # 实际运行

# 查看状态与评分
loopflow state show
loopflow audit . --suggest
```

### Python API

```python
from loopkits import Loop, LoopConfig, TrustLevel
from loopkits.patterns.registry import get

# Code 模式：dry_run 无需凭证
DailyTriage = get("daily-triage")
pattern = DailyTriage()
result = pattern.dry_run()
print(result["report"])

# Work 模式：批量任务 + Comments 轨迹
from loopkits.work import WorkOrchestrator, Task
from loopkits.work.templates import weekly_report_template

config = weekly_report_template()
orch = WorkOrchestrator(config)
batch = orch.run_batch([Task(id="w1", name="周报", payload={})])
print(orch.to_report())
```

## LoopFlow 公式

```
LoopFlow = Loops × WorkFlows + Agents & Services
```

| 组件 | 含义 | LoopKits 实现 |
|------|------|---------------|
| **Loops** | 自治循环：目标 → 执行 → 检查 → 改进 → 重复/停止 | `Loop` / `LoopConfig` / `LoopResult` |
| **WorkFlows** | 有向图步骤串联，多步骤可组合 | `WorkFlow` / `Step` / `RetryPolicy` |
| **Agents** | 四角色执行单元：Maker / Checker / Corrector / Verifier | `Agent` / `AgentRole` |
| **Services** | 外部服务连接器：GitHub / Slack / 邮件 / IMA / HTTP | `Service` / `ServiceRegistry` |

- **Loops × WorkFlows**：循环驱动工作流，工作流编排步骤，循环决定何时停止
- **+ Agents**：四角色分工，Maker 执行、Checker 检查、Corrector 修正、Verifier 验证
- **+ Services**：通过 `service_provider` 抽象外部依赖，无凭证时自动回退 mock

## Code 模式 — 7 个循环模式

| 模式 | 节奏 | 默认级别 | 用途 |
|------|------|----------|------|
| `daily-triage` | `1d` | L1 | 每日扫描 Issue/PR，按 P0/P1/P2/P3 分类并标记需人介入项 |
| `pr-babysitter` | `5m` | L1 | 新 PR 审查：代码风格、测试覆盖、安全问题 |
| `ci-sweeper` | `15m` | L1 | CI 失败分析：分类根因、定位文件、L2 在 worktree 修复 |
| `dependency-sweeper` | `6h` | L1 | 依赖升级：patch 自动 / minor+major 生成评估报告 |
| `changelog-drafter` | `1d` | L1 | 基于 git log 生成 RELEASE_NOTES_DRAFT.md 草案 |
| `post-merge-cleanup` | `1d` | L1 | 合并后清理分支、更新 Issue 状态、标记关闭 |
| `issue-triage` | `2h` | L1 | 新 Issue 自动分析、建议标签、判断优先级 |

**多循环优先级**：CI Sweeper → PR Babysitter → Dependency Sweeper →
Post-Merge / Changelog Drafter（闲时）→ Daily Triage（报告）

详见 `examples/code-mode/` 与 `loopkits/patterns/`。

## Work 模式 — Comments + Corrector

Work 模式在 Code 模式之上增加可审计性与可暂停性，面向办公职员。

### Comments 轨迹

六类结构化注释记录每个任务的处理过程：`DECISION`（决策）、`EVIDENCE`（依据）、
`PENDING`（待确认）、`QUESTION`（提问）、`NEXT_STEP`（下一步建议）、`INFO`（信息）。

### Corrector 门控

| 动作 | 触发条件 | 行为 |
|------|----------|------|
| `PROCEED` | 置信度 ≥ 阈值 且 结果无偏离 | 标记 DONE |
| `PAUSE` | 置信度 < 阈值 | 暂停任务，生成 QUESTION + NEXT_STEP，不阻塞队列 |
| `CORRECT` | 结果偏离规范（含 error / failed / unknown） | 暂停任务，生成修正建议 |

### 3 个任务模板

| 模板 | 调度 | 说明 |
|------|------|------|
| `weekly_report_template()` | 每周一 9:00 | git 提交 → 变更草案 → 周报渲染 → 邮件发送 |
| `email_triage_template()` | 每日 9:00 | 读取未读 → 优先级分类 → 复核 → 标记/回复 |
| `schedule_organize_template()` | 每日 8:00 | 读取日程 → 冲突检测 → 调整建议 |

详见 `examples/work-mode/` 与 `loopkits/work/`。

## CLI 命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `loopflow init [PATH]` | 脚手架初始化 | `loopflow init . --pattern daily-triage --level L1` |
| `loopflow run <PATTERN>` | 运行循环模式 | `loopflow run ci-sweeper --dry-run` |
| `loopflow audit [PATH]` | Loop Ready 评分 | `loopflow audit . --suggest` |
| `loopflow cost <PATTERN>` | Token 费用估算 | `loopflow cost daily-triage --runs 10` |
| `loopflow state` | 状态管理 | `loopflow state show` / `state pause` / `state resume` |
| `loopflow worktree` | git worktree 管理 | `loopflow worktree create --run-id r1 --pattern ci-sweeper` |
| `loopflow skill` | Skill 文档生成 | `loopflow skill list` / `skill generate daily-triage` |
| `loopflow service` | 服务连接器管理 | `loopflow service add github --token ghp_xxx` |

## 服务连接器

| 服务 | 类 | 用途 |
|------|-----|------|
| GitHub | `GitHubService` | Issue / PR / 提交扫描 |
| Slack | `SlackService` | 消息通知与读取 |
| 邮件 | `EmailService` | IMAP 读取 / SMTP 发送 |
| IMA 知识库 | `IMAService` | 知识库笔记与文件管理 |
| HTTP（通用） | `HTTPService` | 任意 REST API 集成 |

所有服务继承 `Service` 基类，支持无凭证 `dry_run`、`health_check` 连通性验证、
`ServiceRegistry` 单例统一注册。

```python
from loopkits.services import GitHubService, EmailService

# 注册服务（也可用 loopflow service add 命令）
github = GitHubService(token="ghp_xxx", repo="owner/repo")
email = EmailService(imap_host="imap.example.com", smtp_host="smtp.example.com",
                     username="user@example.com", password="***")

# 注入到模式或模板
pattern = DailyTriage(service_provider={"github": github})
config.services = {"github": github, "email": email}
```

## 三种分发形态

LoopKits 同一套循环逻辑支持三种分发方式：

| 形态 | 入口 | 适用场景 |
|------|------|----------|
| **Python 库** | `import loopkits` | 编程集成、自定义循环、测试 |
| **CLI 工具** | `loopflow <command>` | 命令行操作、CI/CD 集成、脚手架生成 |
| **Skill 文档** | `loopflow skill generate` | Claude Code / Codex / Cursor 等 AI 工具集成 |

```bash
# CLI 生成 Skill 文档（供 AI 工具使用）
loopflow skill list                          # 列出可导出模式
loopflow skill generate daily-triage         # 生成单个 SKILL.md
loopflow skill master                        # 生成主 Skill 文档

# init 时直接生成 .claude/skills/ 目录
loopflow init . --tool claude --pattern daily-triage
```

## 参考仓库

`references/` 目录包含 3 个参考仓库，提供 Loop Engineering 的原始模式定义、
示例与工具实现，供 LoopKits 借鉴与对照：

| 仓库 | 说明 |
|------|------|
| `references/loop-engineering/` | Loop Engineering 参考实现：7 个模式的原始定义、 starters、工具链（loop-audit / loop-init / loop-cost 等） |
| `references/superpowers/` | 多平台 AI 插件集合：Claude / Codex / Cursor / Grok / OpenCode 等的技能与扩展 |
| `references/autoresearch/` | 自动化研究示例：数据准备与训练脚本 |

> 参考仓库独立于 LoopKits，不参与打包（`pyproject.toml` 中 `exclude = ["references*"]`）。

## 项目结构

```
loopkits/
├── loopkits/                     # 主包
│   ├── __init__.py               # 核心 API 导出
│   ├── core/                     # 核心原语
│   │   ├── loop.py               # Loop / LoopConfig / TrustLevel (L1/L2/L3)
│   │   ├── workflow.py           # WorkFlow / Step / RetryPolicy
│   │   ├── agent.py              # Agent / Maker / Checker / Corrector / Verifier
│   │   ├── state.py              # State（跨迭代状态）
│   │   ├── budget.py             # Budget（Token 预算追踪）
│   │   ├── constraints.py        # Constraints（约束与安全门控）
│   │   └── memory.py             # Memory（棘轮记忆）
│   ├── patterns/                 # Code 模式：7 个循环模式
│   │   ├── registry.py           # 模式注册表
│   │   ├── base.py               # Pattern 抽象基类
│   │   ├── daily_triage.py       # 每日分诊
│   │   ├── pr_babysitter.py      # PR 看护
│   │   ├── ci_sweeper.py         # CI 清扫
│   │   ├── dependency_sweeper.py # 依赖清扫
│   │   ├── changelog_drafter.py  # 变更日志草案
│   │   ├── post_merge_cleanup.py # 合并后清理
│   │   └── issue_triage.py       # Issue 分诊
│   ├── work/                     # Work 模式：办公任务
│   │   ├── orchestrator.py       # WorkOrchestrator / WorkConfig
│   │   ├── corrector.py          # WorkCorrector（置信度门控）
│   │   ├── comments.py           # CommentTrail（结构化注释）
│   │   ├── queue.py              # TaskQueue（任务队列）
│   │   └── templates.py          # 3 个任务模板
│   ├── services/                 # 服务连接器
│   │   ├── base.py               # Service / ServiceRegistry
│   │   ├── github.py             # GitHubService
│   │   ├── slack.py              # SlackService
│   │   ├── email.py              # EmailService
│   │   ├── ima.py                # IMAService
│   │   └── http.py               # HTTPService
│   ├── cli/                      # CLI 命令
│   │   ├── main.py               # loopflow 入口
│   │   ├── init.py               # loopflow init
│   │   ├── run.py                # loopflow run
│   │   ├── audit.py              # loopflow audit
│   │   ├── cost.py               # loopflow cost
│   │   ├── state.py              # loopflow state
│   │   ├── worktree.py           # loopflow worktree
│   │   ├── skill.py              # loopflow skill
│   │   └── service.py            # loopflow service
│   └── skill/                    # Skill 文档生成
│       ├── generator.py          # SKILL.md 生成器
│       ├── claude_code.py        # Claude Code 格式
│       └── codex.py              # Codex 格式
├── examples/                     # 可运行示例
│   ├── code-mode/                # Code 模式示例（dry_run）
│   └── work-mode/                # Work 模式示例（mock 数据）
├── references/                   # 参考仓库（不参与打包）
│   ├── loop-engineering/
│   ├── superpowers/
│   └── autoresearch/
├── tests/                        # 测试
├── pyproject.toml
└── README.MD
```

## 示例

所有示例均可在无凭证环境下直接运行：

```bash
# Code 模式示例
python examples/code-mode/daily_triage_demo.py    # 每日分诊（dry_run）
python examples/code-mode/ci_sweeper_demo.py       # CI 清扫（L1/L2 对比）

# Work 模式示例
python examples/work-mode/weekly_report_demo.py   # 周报生成（mock 数据）
python examples/work-mode/email_triage_demo.py     # 邮件分类（Corrector 暂停）
```

## 许可证

MIT
