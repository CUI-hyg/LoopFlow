# LoopFlow 框架 Spec

> LoopFlow = Loops × WorkFlows + Agents & Services

## Why

当前 AI Agent 与人的协作仍停留在「手动挡」：人逐个喂任务、逐个确认、逐个验证，Agent 无法自主循环工作。
Loop Engineering 已被行业验证为「提示词之后的下一层抽象」（cobusgreyling/loop-engineering 7K★、obra/superpowers 150K★、karpathy/autoresearch 66K★），但现有项目要么是 JS/TS 实现、要么仅面向单一编码场景，缺少一个 **Python 原生、同时覆盖开发与办公、可嵌入也可独立运行** 的实用框架。

LoopFlow 填补这个空白：把「设计循环让 Agent 自动跑」的理念落地为一套 Python 工具链，开发者用 Code 模式管代码循环，办公职员用 Work 模式管任务循环，并通过 CLI 把开放 API 服务接入 LoopFlow。

## What Changes

### 新增：LoopFlow Python 框架（全新项目）

- **核心公式实现**：`LoopFlow = Loops × WorkFlows + Agents & Services`，提供 Loop / WorkFlow / Agent / Service 四类一等原语。
- **双模式架构**：
  - **Code 模式**（面向开发者）：循环模式库 + 工具链 + Skill 形态，可嵌入 Claude Code / Codex。
  - **Work 模式**（面向办公职员）：Comments + Corrector 机制，自动处理大量任务，是 Code 模式的高级封装。
- **三种分发形态**：
  1. Python 库（`import loopflow`）
  2. Skill 形态（生成 `SKILL.md` 嵌入 Claude Code / Codex）
  3. 独立 CLI（`loopflow` 命令，集成开放 API 服务）
- **L1/L2/L3 渐进信任**：L1 只报告、L2 辅助修复（人工监控）、L3 全自动无人值守。
- **参考仓库**：已克隆 3 个示例仓库到 `/workspace/references/`（loop-engineering、superpowers、autoresearch）作为设计参考，单独放置，不混入主项目。

### 设计原则
- Python 优先，最小依赖（标准库 + 少量必要三方库）。
- 不重复造轮子：吸收三个参考仓库的已验证模式（ratchet loop、SKILL.md 自动触发、Loop Ready 评分、worktree 隔离）。
- 实用优先：每个模式都能 `loopflow run <pattern>` 直接跑起来。

## Impact

- **Affected code**：全新项目，无既有代码冲突。主代码位于 `/workspace/loopflow/`。
- **参考仓库**：`/workspace/references/{loop-engineering,superpowers,autoresearch}` 仅作设计参考，不修改。
- **依赖**：Python 3.10+，`click`（CLI）、`pydantic`（数据模型）、`rich`（终端输出）、`gitpython`（worktree）。
- **嵌入目标**：Claude Code（通过 `.claude/skills/`）、Codex（通过 plugin manifest）。

## ADDED Requirements

### Requirement: LoopFlow 核心原语

系统 SHALL 提供四类一等原语，构成 LoopFlow 公式的可组合基础：

1. **Loop**：一次「目标→执行→检查→改进→重复/停止」的自治循环，携带状态与记忆跨迭代。
2. **WorkFlow**：将多个步骤与服务串联成有向图，作为 Loop 的执行体。
3. **Agent**：执行单元，含 Maker（产出）/ Checker（校验）/ Corrector（校正）/ Verifier（验证）四类角色。
4. **Service**：开放 API 服务连接器（GitHub、Slack、邮件、日历、IMA 知识库等），可被 WorkFlow 调用。

#### Scenario: Loop 携带记忆跨迭代
- **WHEN** 一个 Loop 完成第 N 次迭代并产出结果
- **THEN** 第 N+1 次迭代启动时能读取前序迭代的状态、结果与历史（持久化于 state 文件）
- **AND** 若结果未达标则继续循环，达标或触发停止条件则退出

#### Scenario: WorkFlow 串联多服务
- **WHEN** 用户定义一个 WorkFlow：读取 GitHub Issue → 分类 → 分配 → 通知 Slack
- **THEN** 系统按有向图顺序执行各步骤，每步可调用不同 Service
- **AND** 任一步骤失败时按定义的重试/回退策略处理

### Requirement: Code 模式（开发者）

系统 SHALL 提供 Code 模式，专为开发者设计，包含循环模式库、工具链与 Skill 形态。

**循环模式库**（首批 7 个，对标 loop-engineering 已验证模式）：
1. `daily-triage` — 每日扫描 Issue/PR 分类
2. `pr-babysitter` — 新 PR 自动审查
3. `ci-sweeper` — CI 失败自动分析修复
4. `dependency-sweeper` — 依赖升级（patch 自动，minor/major 报告）
5. `changelog-drafter` — 基于 git log 生成 changelog 草案
6. `post-merge-cleanup` — 合并后清理分支/Issue
7. `issue-triage` — 新 Issue 自动打标签/优先级

**工具链命令**（CLI 子命令）：
- `loopflow init` — 脚手架初始化（生成 state/budget/constraints 文件）
- `loopflow run <pattern>` — 运行一个循环模式
- `loopflow audit` — Loop Ready 评分（0-100）+ 改进建议
- `loopflow cost` — Token 费用估算
- `loopflow state` — 查看/管理循环状态
- `loopflow worktree` — 管理 git worktree 隔离
- `loopflow skill export` — 导出为 SKILL.md 嵌入 Claude Code/Codex

#### Scenario: 开发者初始化并运行首个循环
- **WHEN** 开发者在项目根目录执行 `loopflow init --pattern daily-triage --tool claude`
- **THEN** 生成 `LOOP.md`、`STATE.md`、`loop-budget.yaml`、`loop-constraints.md`、`.claude/skills/loop-triage/SKILL.md`
- **AND** 打印 Loop Ready 评分与首条循环命令提示
- **WHEN** 随后执行 `loopflow run daily-triage`
- **THEN** 按 L1（仅报告）级别执行一次扫描，更新 `STATE.md`，不修改代码

#### Scenario: 嵌入 Claude Code 作为 Skill
- **WHEN** 开发者执行 `loopflow skill export --target claude-code --output .claude/skills/`
- **THEN** 生成符合 Claude Code Skill 规范的 `SKILL.md`（含触发条件、步骤、验证）
- **AND** 该 Skill 在 Claude Code 会话中按上下文自动触发，无需手动调用

### Requirement: Work 模式（办公职员）

系统 SHALL 提供 Work 模式，作为 Code 模式的高级封装，面向办公职员自动处理大量任务。

**核心机制 — Comments + Corrector**：
- **Comments**：系统对每个任务的处理过程以结构化注释记录（决策、依据、待确认项），形成可审计轨迹。
- **Corrector**：当系统不确定或偏离规范时，Corrector Agent 主动提出问题或下一步操作建议，由人确认后继续。

**Work 模式特性**：
- 主动/自动批量处理任务队列
- 通过 Comments 暴露决策过程，Corrector 在关键节点请求人工校正
- 及时提出问题或下一步操作（而非盲目执行）
- 本质是 Code 模式循环 + WorkFlow + 服务连接器的高级编排

#### Scenario: Corrector 主动请求人工确认
- **GIVEN** Work 模式正在自动处理一批邮件分类任务
- **WHEN** 遇到一封无法确定优先级的邮件（置信度低于阈值）
- **THEN** Corrector 暂停该任务，在 Comments 中记录「不确定原因 + 两个候选分类 + 建议下一步」
- **AND** 通知用户确认后继续，其余任务不受阻塞继续处理

#### Scenario: Work 模式封装 Code 模式循环
- **WHEN** 用户定义一个 Work 任务：「每周一生成上周项目周报并发送给团队」
- **THEN** 系统将其编译为一个 WorkFlow（拉取 git log → 调 changelog-drafter 循环 → 渲染模板 → 调邮件 Service 发送）
- **AND** 该 WorkFlow 被一个 Loop 以周为节奏调度，每次执行产出 Comments 轨迹

### Requirement: CLI 与开放 API 服务集成

独立 CLI（`loopflow`）SHALL 提供高级能力：将开放 API 的软件服务接入 LoopFlow，并通过 WorkFlow 串联。

**首批服务连接器**：
- GitHub（Issue/PR 读写）
- Slack（消息读写）
- 邮件（IMAP/SMTP）
- IMA 知识库（搜索/上传，复用 ima-skill）
- 通用 HTTP（任意 REST API）

#### Scenario: 通过 CLI 接入新服务
- **WHEN** 用户执行 `loopflow service add github --token $GH_TOKEN`
- **THEN** 服务凭证安全存储（不落明文），并在 WorkFlow 中可通过 `service("github")` 引用
- **AND** `loopflow service list` 列出已接入服务及其健康状态

### Requirement: 安全与渐进信任

系统 SHALL 强制安全门控，防止 Agent 失控：

- **路径保护**：默认禁止编辑 `.env`、`secrets/`、`credentials/`、基础设施配置。
- **预算控制**：Token 花费达 80% 日上限时切换为仅报告模式；`loop-pause-all` 标志触发立即退出。
- **Worktree 隔离**：所有无人值守的代码变更实验在独立 git worktree 中进行，验证通过才合并。
- **L1/L2/L3 分级**：新模式默认从 L1（仅报告）起步，验证可靠后逐步升级到 L2（辅助修复）、L3（全自动）。
- **Constraints 文件**：`loop-constraints.md` 中的规则对 Agent 具有约束力（不自动合并 main、不关闭 Issue 未经批准等）。

#### Scenario: 预算耗尽自动降级
- **GIVEN** 一个 L2 级循环正在自动修复 CI 失败
- **WHEN** 本次循环 Token 消耗达到日预算 80%
- **THEN** 循环立即切换为 L1 仅报告模式，停止代码修改
- **AND** 在 STATE.md 记录降级事件与原因

## 参考仓库说明

以下 3 个仓库已克隆到 `/workspace/references/`，作为设计参考（单独放置，不混入主项目，不修改）：

| 仓库 | 语言 | 借鉴点 |
|------|------|--------|
| `cobusgreyling/loop-engineering` | JS/TS | 7 个循环模式、Loop Ready 评分、L1/L2/L3 信任分级、constraints/budget/state 文件、worktree 隔离、MCP 连接器 |
| `obra/superpowers` | Markdown | SKILL.md 自动触发机制、brainstorm→plan→execute 流水线、SDD（子代理驱动开发）、TDD 强制、跨平台嵌入（Claude Code/Codex/Cursor） |
| `karpathy/autoresearch` | Python | 三文件架构（prepare/train/program）、ratchet loop（棘轮循环：只保留改进）、标量指标驱动、git 作为记忆、`program.md` 作为人机接口、NEVER STOP 自治 |

LoopFlow 的 Python 实现综合三者：以 autoresearch 的 Python 风格为骨架，吸收 loop-engineering 的模式库与评分体系，采用 superpowers 的 Skill 形态与触发机制。
