# Work 模式示例

LoopFlow 的 **Work 模式**面向办公职员，在 Code 模式之上提供 Comments 轨迹与
Corrector 门控机制，让自动化任务可审计、可暂停、可恢复。

## Comments + Corrector 机制

### Comments 轨迹

Work 模式的核心审计机制。每个任务的处理过程都记录为结构化注释，按任务分组
形成可追溯的时间线。六类注释：

| 类型 | 图标 | 说明 |
|------|------|------|
| `DECISION` | 📋 | 决策（如「开始执行任务」「将邮件分类为高优先级」） |
| `EVIDENCE` | 🔍 | 依据（如「邮件包含紧急关键词」「置信度 0.90」） |
| `PENDING` | ⏳ | 待确认（如「任务已暂停：置信度不足」） |
| `QUESTION` | ❓ | 提问（如「置信度 0.90 低于阈值 0.95，请确认如何处理？」） |
| `NEXT_STEP` | ➡️ | 下一步建议（如「建议人工审核后通过 resume() 恢复」） |
| `INFO` | ℹ️ | 信息（如「任务完成：置信度充足且结果符合规范」） |

### Corrector 门控

每个任务执行后，Corrector 检查结果置信度，返回三种动作之一：

| 动作 | 触发条件 | 行为 |
|------|----------|------|
| `PROCEED` | 置信度 ≥ 阈值 且 结果无偏离 | 标记为 DONE，记录 INFO 注释 |
| `PAUSE` | 置信度 < 阈值 | 标记为 PAUSED，生成 QUESTION + NEXT_STEP + PENDING |
| `CORRECT` | 置信度 ≥ 阈值 但 结果偏离规范 | 标记为 PAUSED，生成 EVIDENCE + NEXT_STEP（含修正建议） |

**单任务暂停不阻塞队列**：一个任务 PAUSE 后，队列继续处理下一个 PENDING 任务。
人工处理后通过 `orchestrator.resume(task_id, decision)` 恢复。

## 3 个任务模板

| 模板 | 调度 | 所需服务 | 说明 |
|------|------|----------|------|
| `weekly_report_template()` | 每周一 9:00 | github, email | 扫描 git 提交 → 生成变更草案 → 渲染周报 → 邮件发送 |
| `email_triage_template()` | 每日 9:00 | email | 读取未读邮件 → 按优先级分类 → 复核 → 标记/回复 |
| `schedule_organize_template()` | 每日 8:00 | http | 读取日程 → 检测时间冲突 → 生成调整建议 |

所有模板都支持无凭证 `dry_run`：服务缺失时自动回退到内置 mock 数据。

## 示例文件

| 文件 | 说明 |
|------|------|
| `weekly_report_demo.py` | 周报生成：批量执行、Comments 轨迹、报告提取 |
| `email_triage_demo.py` | 邮件分类：Corrector 暂停机制、人工恢复、L1/L2 对比 |

## 运行示例

```bash
# 周报生成演示
python examples/work-mode/weekly_report_demo.py

# 邮件分类演示（含 Corrector 暂停）
python examples/work-mode/email_triage_demo.py
```

## 核心 API

```python
from loopflow.work import WorkOrchestrator, WorkConfig, Task, WorkCorrector
from loopflow.work.templates import weekly_report_template, email_triage_template

# 加载模板
config = weekly_report_template()

# 构造编排器
orch = WorkOrchestrator(config)

# 批量执行
tasks = [
    Task(id="w1", name="项目A周报", payload={"project": "a"}),
    Task(id="w2", name="项目B周报", payload={"project": "b"}),
]
batch = orch.run_batch(tasks)
print(f"完成 {batch.done}，暂停 {batch.paused}")

# 查看暂停任务
for t in orch.paused_tasks():
    print(f"暂停：{t.id} — {t.paused_reason}")

# 人工恢复
orch.resume("w1", "proceed")

# 完整报告
print(orch.to_report())
```

## 自定义 Corrector 阈值

```python
from loopflow.work.corrector import WorkCorrector

# 默认阈值 0.7；提高阈值可让 Corrector 更严格
config = email_triage_template()
config.corrector = WorkCorrector(confidence_threshold=0.95)
```
