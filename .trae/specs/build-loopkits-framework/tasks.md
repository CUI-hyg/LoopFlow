# Tasks

> 实现顺序：核心原语 → Code 模式 → Work 模式 → CLI/服务集成 → Skill 导出 → 文档与示例

- [x] Task 1: 搭建项目骨架与核心原语
  - [x] SubTask 1.1: 创建 `loopflow/` 包结构（`core/`、`patterns/`、`work/`、`agents/`、`services/`、`cli/`、`skill/`），`pyproject.toml`，最小依赖（click/pydantic/rich/gitpython）
  - [x] SubTask 1.2: 实现 `core/loop.py` — Loop 原语（目标→执行→检查→改进→重复/停止），携带状态跨迭代，支持停止条件与最大迭代数
  - [x] SubTask 1.3: 实现 `core/workflow.py` — WorkFlow 原语（有向图步骤串联，含重试/回退策略）
  - [x] SubTask 1.4: 实现 `core/agent.py` — Agent 基类与 Maker/Checker/Corrector/Verifier 四角色
  - [x] SubTask 1.5: 实现 `core/state.py` — 状态持久化（STATE.md 读写 + JSON 结构化状态）
  - [x] SubTask 1.6: 实现 `core/budget.py` — Token 预算追踪与 80% 降级逻辑
  - [x] SubTask 1.7: 实现 `core/constraints.py` — 解析 `loop-constraints.md` 为可编程约束（路径保护、行为规则）
  - [x] SubTask 1.8: 实现 `core/memory.py` — 跨迭代记忆（ratchet 机制：只保留改进，git 作为记忆）

- [x] Task 2: 实现 Code 模式循环模式库
  - [x] SubTask 2.1: 定义 `patterns/base.py` — Pattern 基类（元数据、L1/L2/L3 配置、验证器接口）
  - [x] SubTask 2.2: 实现 `patterns/daily_triage.py` — 每日 Issue/PR 分类扫描
  - [x] SubTask 2.3: 实现 `patterns/pr_babysitter.py` — 新 PR 自动审查
  - [x] SubTask 2.4: 实现 `patterns/ci_sweeper.py` — CI 失败分析与修复
  - [x] SubTask 2.5: 实现 `patterns/dependency_sweeper.py` — 依赖升级（patch 自动/minor-major 报告）
  - [x] SubTask 2.6: 实现 `patterns/changelog_drafter.py` — git log 生成 changelog 草案
  - [x] SubTask 2.7: 实现 `patterns/post_merge_cleanup.py` — 合并后清理
  - [x] SubTask 2.8: 实现 `patterns/issue_triage.py` — 新 Issue 自动打标签
  - [x] SubTask 2.9: 创建 `patterns/registry.py` — 模式注册表与发现机制

- [x] Task 3: 实现 CLI 工具链
  - [x] SubTask 3.1: 实现 `cli/main.py` — `loopflow` 入口与子命令路由（click）
  - [x] SubTask 3.2: 实现 `cli/init.py` — `loopflow init` 脚手架（生成 LOOP.md/STATE.md/budget/constraints/skill）
  - [x] SubTask 3.3: 实现 `cli/run.py` — `loopflow run <pattern>` 运行循环
  - [x] SubTask 3.4: 实现 `cli/audit.py` — `loopflow audit` Loop Ready 评分（0-100）+ 建议
  - [x] SubTask 3.5: 实现 `cli/cost.py` — `loopflow cost` Token 费用估算
  - [x] SubTask 3.6: 实现 `cli/state.py` — `loopflow state` 查看/管理状态
  - [x] SubTask 3.7: 实现 `cli/worktree.py` — `loopflow worktree` git worktree 隔离管理
  - [x] SubTask 3.8: 实现 `cli/skill_export.py` — `loopflow skill export` 导出 SKILL.md

- [x] Task 4: 实现 Work 模式（Comments + Corrector）
  - [x] SubTask 4.1: 实现 `work/comments.py` — 结构化注释轨迹（决策/依据/待确认项/时间线）
  - [x] SubTask 4.2: 实现 `work/corrector.py` — Corrector Agent（置信度阈值、主动提问、下一步建议）
  - [x] SubTask 4.3: 实现 `work/queue.py` — 任务队列与批量调度（单任务暂停不阻塞其他）
  - [x] SubTask 4.4: 实现 `work/orchestrator.py` — Work 模式编排器（封装 Code 循环 + WorkFlow + 服务）
  - [x] SubTask 4.5: 实现 `work/templates.py` — 常见 Work 任务模板（周报、邮件分类、日程整理）

- [x] Task 5: 实现服务连接器
  - [x] SubTask 5.1: 定义 `services/base.py` — Service 基类（健康检查、凭证安全存储）
  - [x] SubTask 5.2: 实现 `services/github.py` — GitHub Issue/PR 读写
  - [x] SubTask 5.3: 实现 `services/slack.py` — Slack 消息读写
  - [x] SubTask 5.4: 实现 `services/email.py` — IMAP/SMTP 邮件
  - [x] SubTask 5.5: 实现 `services/ima.py` — IMA 知识库（复用 ima-skill 凭证与环境变量）
  - [x] SubTask 5.6: 实现 `services/http.py` — 通用 REST API 连接器
  - [x] SubTask 5.7: 实现 `cli/service.py` — `loopflow service add/list/health` 命令

- [x] Task 6: 实现 Skill 导出与嵌入
  - [x] SubTask 6.1: 实现 `skill/generator.py` — 从 Pattern 生成 SKILL.md（触发条件、步骤、验证）
  - [x] SubTask 6.2: 实现 Claude Code 嵌入目标（`.claude/skills/` 布局 + 自动触发）
  - [x] SubTask 6.3: 实现 Codex 嵌入目标（plugin manifest）
  - [x] SubTask 6.4: 创建主 Skill `using-loopflow`（会话启动注入，强制使用相关模式）

- [x] Task 7: 安全门控与渐进信任
  - [x] SubTask 7.1: 实现路径保护（默认禁止编辑 .env/secrets/credentials/基础设施配置）
  - [x] SubTask 7.2: 实现预算耗尽自动降级（L2→L1）与 `loop-pause-all` 杀停开关
  - [x] SubTask 7.3: 实现 worktree 隔离强制（无人值守代码变更必须在 worktree）
  - [x] SubTask 7.4: 实现 L1/L2/L3 配置与升级路径（新模式默认 L1）

- [x] Task 8: 示例与文档
  - [x] SubTask 8.1: 创建 `examples/code-mode/` 示例（daily-triage、ci-sweeper 各一个可运行 demo）
  - [x] SubTask 8.2: 创建 `examples/work-mode/` 示例（周报生成、邮件分类各一个 demo）
  - [x] SubTask 8.3: 更新根 `README.MD`（项目介绍、快速开始、模式列表、LoopFlow 公式说明）
  - [x] SubTask 8.4: 创建 `LOOP.md` 模板与 `loop-constraints.md` 模板

- [x] Task 9: 测试验证
  - [x] SubTask 9.1: 核心原语单元测试（loop/workflow/agent/state/budget/constraints）
  - [x] SubTask 9.2: 模式库冒烟测试（每个 pattern 能 dry-run）
  - [x] SubTask 9.3: CLI 集成测试（init→audit→run 完整流程）
  - [x] SubTask 9.4: Work 模式 Corrector 流程测试（置信度阈值触发暂停）

# Task Dependencies

- Task 2 依赖 Task 1（模式库基于核心原语）
- Task 3 依赖 Task 1、Task 2（CLI 调用核心与模式）
- Task 4 依赖 Task 1、Task 2（Work 模式封装 Code 循环）
- Task 5 可与 Task 2/3/4 部分并行（Service 基类独立，具体连接器被 Work 模式调用）
- Task 6 依赖 Task 2（从 Pattern 生成 Skill）
- Task 7 贯穿 Task 1-5（安全门控嵌入各层）
- Task 8 依赖 Task 1-7
- Task 9 依赖 Task 1-8
