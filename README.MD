# LoopFlow

> **LoopFlow = Loops × WorkFlows + Agents & Services**

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-63%20passed-brightgreen.svg)](tests/)
[![Security](https://img.shields.io/badge/security-29%20fixes-red.svg)](scripts/security_verify.py)
[![Canary-dev Gate](https://github.com/CUI-hyg/LoopFlow/actions/workflows/canary-dev-gate.yml/badge.svg?branch=Canary-dev)](https://github.com/CUI-hyg/LoopFlow/actions/workflows/canary-dev-gate.yml)

LoopFlow 是一个 Python 原生的 **Loop Engineering** 框架，将自治循环（Loops）、
工作流（WorkFlows）、智能体（Agents）与服务连接器（Services）整合为统一的
编程模型，让 AI 驱动的开发与办公自动化可组合、可审计、可信任。

## 目录

- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [LoopFlow 公式](#loopflow-公式)
- [Code 模式 — 7 个循环模式](#code-模式--7-个循环模式)
- [Work 模式 — Comments + Corrector](#work-模式--comments--corrector)
- [CLI 命令](#cli-命令)
- [服务连接器](#服务连接器)
- [三种分发形态](#三种分发形态)
- [安全与门控](#安全与门控)
- [CI/CD 自动化](#cicd-自动化)
- [项目结构](#项目结构)
- [示例](#示例)
- [参考仓库](#参考仓库)
- [许可证](#许可证)

## 核心特性

- **双模式**：Code 模式（7 个开发循环模式）+ Work 模式（办公任务模板 + Comments 轨迹）
- **三形态**：Python 库 / CLI 工具 / Skill 文档，同一套循环逻辑三种分发方式
- **三级信任**：L1 仅报告 / L2 辅助修复（worktree + verifier）/ L3 全自动（严格约束门控）
- **安全门控**：路径保护（denylist）、预算追踪、kill switch、Constraints 约束文件、HMAC 状态签名
- **红客审计**：经 29 处漏洞修复 + 23 项渗透验证用例覆盖（SSRF / 路径遍历 / 注入 / 权限绕过）
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
from loopflow import Loop, LoopConfig, TrustLevel
from loopflow.patterns.registry import get

# Code 模式：dry_run 无需凭证
DailyTriage = get("daily-triage")
pattern = DailyTriage()
result = pattern.dry_run()
print(result["report"])

# Work 模式：批量任务 + Comments 轨迹
from loopflow.work import WorkOrchestrator, Task
from loopflow.work.templates import weekly_report_template

config = weekly_report_template()
orch = WorkOrchestrator(config)
batch = orch.run_batch([Task(id="w1", name="周报", payload={})])
print(orch.to_report())
```

## LoopFlow 公式

```
LoopFlow = Loops × WorkFlows + Agents & Services
```

| 组件 | 含义 | LoopFlow 实现 |
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

详见 `examples/code-mode/` 与 `loopflow/patterns/`。

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

详见 `examples/work-mode/` 与 `loopflow/work/`。

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
`ServiceRegistry` 单例统一注册，凭证文件经 Base64 编码 + `0o600` 权限保护。

```python
from loopflow.services import GitHubService, EmailService

# 注册服务（也可用 loopflow service add 命令）
github = GitHubService(token="ghp_xxx", repo="owner/repo")
email = EmailService(imap_host="imap.example.com", smtp_host="smtp.example.com",
                     username="user@example.com", password="***")

# 注入到模式或模板
pattern = DailyTriage(service_provider={"github": github})
config.services = {"github": github, "email": email}
```

## 三种分发形态

LoopFlow 同一套循环逻辑支持三种分发方式：

| 形态 | 入口 | 适用场景 |
|------|------|----------|
| **Python 库** | `import loopflow` | 编程集成、自定义循环、测试 |
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

## 安全与门控

LoopFlow 内置多层安全护栏，经红客渗透审计验证：

### 路径保护

默认禁止编辑 `.env` / `secrets/` / `credentials/` / 基础设施配置，段级匹配防止子目录绕过。

### 预算追踪

Token 预算耗尽自动降级（L2→L1），`loop-pause-all` 杀停开关，字段级校验防止负数绕过。

### 状态完整性

`State` 支持 HMAC-SHA256 签名（`LOOPKITS_STATE_SECRET` 环境变量），文件权限 `0o600`。

### SSRF 防护

`HTTPService` 内网 IP 黑名单（169.254/10/172.16/192.168/127），禁用自动重定向。

### 凭证安全

- `services.json` 权限 `0o600`，凭证 Base64 编码（非明文落盘）
- IMA 凭证通过 `env=` 字典传递，不暴露在命令行
- 邮件头 CRLF 注入清洗（`_sanitize_header`）

### 渗透验证

```bash
# 运行 23 项渗透验证用例
python scripts/security_verify.py
```

覆盖：路径黑名单绕过、SSRF 内网访问、worktree 路径遍历、预算负数绕过、邮件头注入、
HMAC 签名篡改、凭证文件权限、CI sweeper 永真判断、IMA 凭证暴露等。

## CI/CD 自动化

### Canary-dev 自动门控

针对 `Canary-dev` 分支的 PR 自动触发质量检查与合并：

```yaml
# .github/workflows/canary-dev-gate.yml
触发: PR → Canary-dev (opened / synchronize / reopened)
流程:
  1. 质量检查: pytest + security_verify + 导入冒烟 + CLI 冒烟
  2. 自动合并: squash merge（仅当质量检查通过）
护栏:
  - 仅 Canary-dev 分支自动合并（main/master 永不自动合并）
  - PR 带 no-auto-merge 标签时跳过
  - 合并后自动删除 trae/agent-* 源分支
```

## 项目结构

```
loopflow/
├── loopflow/                     # 主包
│   ├── __init__.py               # 核心 API 导出
│   ├── core/                     # 核心原语
│   │   ├── loop.py               # Loop / LoopConfig / TrustLevel (L1/L2/L3)
│   │   ├── workflow.py           # WorkFlow / Step / RetryPolicy
│   │   ├── agent.py              # Agent / Maker / Checker / Corrector / Verifier
│   │   ├── state.py              # State（跨迭代状态 + HMAC 签名）
│   │   ├── budget.py             # Budget（Token 预算追踪 + 字段校验）
│   │   ├── constraints.py        # Constraints（约束与安全门控）
│   │   ├── safety.py             # Safety（worktree 隔离强制）
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
│   │   ├── base.py               # Service / ServiceRegistry（0o600 权限）
│   │   ├── github.py             # GitHubService（state 白名单）
│   │   ├── slack.py              # SlackService
│   │   ├── email.py              # EmailService（CRLF 清洗）
│   │   ├── ima.py                # IMAService（env 传递凭证）
│   │   └── http.py               # HTTPService（SSRF 防护）
│   ├── cli/                      # CLI 命令
│   │   ├── main.py               # loopflow 入口
│   │   ├── init.py               # loopflow init
│   │   ├── run.py                # loopflow run
│   │   ├── audit.py              # loopflow audit
│   │   ├── cost.py               # loopflow cost（IntRange 校验）
│   │   ├── state.py              # loopflow state
│   │   ├── worktree.py           # loopflow worktree（路径遍历防护）
│   │   ├── skill.py              # loopflow skill
│   │   └── service.py            # loopflow service
│   └── skill/                    # Skill 文档生成
│       ├── generator.py          # SKILL.md 生成器（YAML 转义）
│       ├── claude_code.py        # Claude Code 格式
│       └── codex.py              # Codex 格式
├── .github/workflows/            # CI/CD 自动化
│   └── canary-dev-gate.yml       # Canary-dev 自动门控
├── examples/                     # 可运行示例
│   ├── code-mode/                # Code 模式示例（dry_run）
│   └── work-mode/                # Work 模式示例（mock 数据）
├── references/                   # 参考仓库（不参与打包）
├── scripts/                      # 工具脚本
│   └── security_verify.py        # 渗透验证脚本（23 项）
├── tests/                        # 测试（63 个用例）
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

## 参考仓库

`references/` 目录包含 3 个参考仓库，提供 Loop Engineering 的原始模式定义、
示例与工具实现，供 LoopFlow 借鉴与对照：

| 仓库 | 说明 |
|------|------|
| `references/loop-engineering/` | Loop Engineering 参考实现：7 个模式的原始定义、 starters、工具链（loop-audit / loop-init / loop-cost 等） |
| `references/superpowers/` | 多平台 AI 插件集合：Claude / Codex / Cursor / Grok / OpenCode 等的技能与扩展 |
| `references/autoresearch/` | 自动化研究示例：数据准备与训练脚本 |

> 参考仓库独立于 LoopFlow，不参与打包（`pyproject.toml` 中 `exclude = ["references*"]`）。

## 许可证

MIT
