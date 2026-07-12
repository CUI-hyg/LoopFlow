"""常见 Work 任务模板。

预定义三个常见办公任务的 WorkFlow 模板，每个返回一个 :class:`WorkConfig`，
含预构建的 WorkFlow（Step 串联）和所需服务列表。所有模板都能无凭证 dry_run
（用 mock 数据）。

模板：

- :func:`weekly_report_template` — 每周项目周报（git log → 草案 → 渲染 → 邮件）
- :func:`email_triage_template` — 邮件分类（读取未读 → 分类 → 复核 → 标记/回复）
- :func:`schedule_organize_template` — 日程整理（读取日程 → 冲突检测 → 建议）

每个 Step 的 action 通过 ``ctx["services"]`` 获取真实服务；服务缺失时回退到
mock 数据，保证无凭证环境下也能 dry_run。
"""

from __future__ import annotations

from typing import Any

from loopkits.core.workflow import Step, WorkFlow
from loopkits.work.corrector import WorkCorrector
from loopkits.work.orchestrator import WorkConfig

__all__ = [
    "weekly_report_template",
    "email_triage_template",
    "schedule_organize_template",
]


# ====================================================================== #
# 模板 1：每周项目周报
# ====================================================================== #

def weekly_report_template() -> WorkConfig:
    """每周项目周报模板。

    WorkFlow 步骤：

    1. ``fetch-commits`` — 获取本周 git 提交（github 服务 / mock）
    2. ``draft-changelog`` — 按 conventional commits 分类生成变更草案
    3. ``render-report`` — 渲染周报 Markdown
    4. ``send-email`` — 邮件发送（email 服务 / dry_run 打印）

    所需服务：``github``、``email``
    """
    workflow = WorkFlow(
        name="weekly-report",
        steps=[
            Step(
                name="fetch-commits",
                action=_weekly_fetch_commits,
                outputs="commits",
            ),
            Step(
                name="draft-changelog",
                action=_weekly_draft_changelog,
                outputs="changelog",
            ),
            Step(
                name="render-report",
                action=_weekly_render_report,
                outputs="report",
            ),
            Step(
                name="send-email",
                action=_weekly_send_email,
                outputs="sent",
            ),
        ],
    )
    return WorkConfig(
        name="每周项目周报",
        description="扫描本周 git 提交，生成变更草案并渲染周报，邮件发送",
        pattern_name="changelog-drafter",
        workflow=workflow,
        required_services=["github", "email"],
        corrector=WorkCorrector(confidence_threshold=0.7),
        schedule="0 9 * * 1",  # 每周一 9:00
    )


def _weekly_fetch_commits(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """获取本周提交。优先使用 github 服务，否则返回 mock 数据。"""
    services = ctx.get("services", {})
    github = services.get("github")
    if github is not None and github.has_credentials():
        # 真实服务：通过 GitHub API 获取本周提交
        try:
            commits = github.list_issues(state="all")  # 简化：复用 list_issues
            if commits:
                return commits
        except Exception as exc:  # noqa: BLE001
            # 服务异常时记录警告并降低置信度，避免静默回退到 mock 数据
            ctx["confidence"] = 0.3
            ctx.setdefault("_warnings", []).append(
                f"github 服务调用失败，回退到 mock 数据：{type(exc).__name__}: {exc}"
            )
    return list(_MOCK_WEEKLY_COMMITS)


def _weekly_draft_changelog(ctx: dict[str, Any]) -> dict[str, Any]:
    """按 conventional commits 分类生成变更草案。"""
    commits = ctx.get("commits", [])
    features: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []
    breaking: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []

    for commit in commits:
        message = commit.get("message", commit.get("title", ""))
        sha = commit.get("sha", commit.get("id", "?"))
        if isinstance(sha, int):
            sha = str(sha)
        author = commit.get("author", commit.get("user", "unknown"))
        first_line = message.split("\n")[0].strip()
        is_breaking = "BREAKING" in message or "!" in first_line.split(":")[0]

        entry = {
            "sha": str(sha)[:8],
            "description": first_line,
            "author": author,
            "breaking": is_breaking,
        }
        if is_breaking:
            breaking.append(entry)
        elif first_line.lower().startswith("feat"):
            features.append(entry)
        elif first_line.lower().startswith("fix"):
            fixes.append(entry)
        else:
            others.append(entry)

    return {
        "features": features,
        "fixes": fixes,
        "breaking_changes": breaking,
        "others": others,
        "total": len(commits),
    }


def _weekly_render_report(ctx: dict[str, Any]) -> str:
    """渲染周报 Markdown。"""
    changelog = ctx.get("changelog", {})
    lines = [
        "# 项目周报",
        "",
        f"> 本周共 {changelog.get('total', 0)} 个变更",
        "",
    ]
    if changelog.get("breaking_changes"):
        lines.append("## ⚠️ Breaking Changes")
        lines.append("")
        for c in changelog["breaking_changes"]:
            lines.append(f"- **{c['sha']}** {c['description']} (@{c['author']})")
        lines.append("")

    if changelog.get("features"):
        lines.append("## ✨ 新功能")
        lines.append("")
        for c in changelog["features"]:
            lines.append(f"- {c['description']} (`{c['sha']}`)")
        lines.append("")

    if changelog.get("fixes"):
        lines.append("## 🐛 修复")
        lines.append("")
        for c in changelog["fixes"]:
            lines.append(f"- {c['description']} (`{c['sha']}`)")
        lines.append("")

    if changelog.get("others"):
        lines.append("## 📦 其他变更")
        lines.append("")
        for c in changelog["others"]:
            lines.append(f"- {c['description']} (`{c['sha']}`)")
        lines.append("")

    # 设置置信度（有提交时高置信度）
    ctx["confidence"] = 0.9 if changelog.get("total", 0) > 0 else 0.5
    return "\n".join(lines)


def _weekly_send_email(ctx: dict[str, Any]) -> bool:
    """发送周报邮件。优先使用 email 服务，否则 dry_run。"""
    report = ctx.get("report", "")
    services = ctx.get("services", {})
    email_svc = services.get("email")
    if email_svc is not None and email_svc.has_credentials():
        try:
            return email_svc.send(
                to="team@example.com",
                subject="项目周报",
                body=report,
            )
        except Exception:  # noqa: BLE001
            return False
    # dry_run：打印到 stdout 模拟发送
    print("[dry_run] 周报邮件未发送（无 email 凭证），内容已生成")
    return False


# ====================================================================== #
# 模板 2：邮件分类
# ====================================================================== #

def email_triage_template() -> WorkConfig:
    """邮件分类模板。

    WorkFlow 步骤：

    1. ``read-unread`` — 读取未读邮件（email 服务 / mock）
    2. ``classify-priority`` — 按优先级分类（高/中/低）
    3. ``review-classification`` — 复核分类质量，设置置信度
    4. ``mark-reply`` — 标记或生成回复

    所需服务：``email``
    """
    workflow = WorkFlow(
        name="email-triage",
        steps=[
            Step(
                name="read-unread",
                action=_email_read_unread,
                outputs="emails",
            ),
            Step(
                name="classify-priority",
                action=_email_classify,
                outputs="classified",
            ),
            Step(
                name="review-classification",
                action=_email_review,
                outputs="reviewed",
            ),
            Step(
                name="mark-reply",
                action=_email_mark_reply,
                outputs="actions",
            ),
        ],
    )
    return WorkConfig(
        name="邮件分类",
        description="读取未读邮件，按优先级分类并复核，标记或生成回复",
        workflow=workflow,
        required_services=["email"],
        corrector=WorkCorrector(confidence_threshold=0.7),
        schedule="0 9 * * *",  # 每日 9:00
    )


def _email_read_unread(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """读取未读邮件。优先使用 email 服务，否则返回 mock 数据。"""
    services = ctx.get("services", {})
    email_svc = services.get("email")
    if email_svc is not None and email_svc.has_credentials():
        try:
            emails = email_svc.list_unread(limit=20)
            if emails:
                return emails
        except Exception as exc:  # noqa: BLE001
            # 服务异常时记录警告并降低置信度，避免静默回退到 mock 数据
            ctx["confidence"] = 0.3
            ctx.setdefault("_warnings", []).append(
                f"email 服务调用失败，回退到 mock 数据：{type(exc).__name__}: {exc}"
            )
    return list(_MOCK_EMAILS)


def _email_classify(ctx: dict[str, Any]) -> dict[str, Any]:
    """按优先级分类邮件（高/中/低）。"""
    emails = ctx.get("emails", [])
    high: list[dict[str, Any]] = []
    medium: list[dict[str, Any]] = []
    low: list[dict[str, Any]] = []

    for email_item in emails:
        subject = email_item.get("subject", "")
        body = email_item.get("body", "")
        text = f"{subject} {body}".lower()

        entry = {
            **email_item,
            "priority": "medium",
            "reason": "",
        }

        # 高优先级：紧急关键词
        if any(k in text for k in ("紧急", "urgent", "asap", "critical", "立即", "马上")):
            entry["priority"] = "high"
            entry["reason"] = "包含紧急关键词"
            high.append(entry)
        # 低优先级：通知/订阅
        elif any(k in text for k in ("newsletter", "通知", "订阅", "digest", "周报")):
            entry["priority"] = "low"
            entry["reason"] = "通知/订阅类邮件"
            low.append(entry)
        else:
            entry["reason"] = "常规邮件"
            medium.append(entry)

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "total": len(emails),
    }


def _email_review(ctx: dict[str, Any]) -> dict[str, Any]:
    """复核分类质量，设置置信度。

    如果有邮件无法明确分类（既不匹配高也不匹配低），降低置信度。
    """
    classified = ctx.get("classified", {})
    total = classified.get("total", 0)
    high_count = len(classified.get("high", []))
    medium_count = len(classified.get("medium", []))
    low_count = len(classified.get("low", []))

    # 置信度评估：如果 medium 占比过高，说明分类不够明确
    if total == 0:
        confidence = 1.0
    else:
        medium_ratio = medium_count / total
        if medium_ratio > 0.6:
            # 多数邮件归为 medium，分类不够明确
            confidence = 0.5
        elif medium_ratio > 0.3:
            confidence = 0.7
        else:
            confidence = 0.9

    ctx["confidence"] = confidence
    return {
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "confidence": confidence,
    }


def _email_mark_reply(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """标记或生成回复。"""
    classified = ctx.get("classified", {})
    actions: list[dict[str, Any]] = []

    for email_item in classified.get("high", []):
        actions.append({
            "email": email_item.get("subject", ""),
            "action": "flag_high_priority",
            "reply": f"已标记为高优先级：{email_item.get('reason', '')}",
        })

    for email_item in classified.get("low", []):
        actions.append({
            "email": email_item.get("subject", ""),
            "action": "archive",
            "reply": f"已归档：{email_item.get('reason', '')}",
        })

    return actions


# ====================================================================== #
# 模板 3：日程整理
# ====================================================================== #

def schedule_organize_template() -> WorkConfig:
    """日程整理模板。

    WorkFlow 步骤：

    1. ``read-schedule`` — 读取日程（http 服务 / mock）
    2. ``detect-conflicts`` — 冲突检测
    3. ``generate-suggestions`` — 生成建议

    所需服务：``http``（日历 API）
    """
    workflow = WorkFlow(
        name="schedule-organize",
        steps=[
            Step(
                name="read-schedule",
                action=_schedule_read,
                outputs="events",
            ),
            Step(
                name="detect-conflicts",
                action=_schedule_detect_conflicts,
                outputs="conflicts",
            ),
            Step(
                name="generate-suggestions",
                action=_schedule_suggestions,
                outputs="suggestions",
            ),
        ],
    )
    return WorkConfig(
        name="日程整理",
        description="读取日程，检测时间冲突并生成调整建议",
        workflow=workflow,
        required_services=["http"],
        corrector=WorkCorrector(confidence_threshold=0.7),
        schedule="0 8 * * *",  # 每日 8:00
    )


def _schedule_read(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """读取日程。优先使用 http 服务，否则返回 mock 数据。"""
    services = ctx.get("services", {})
    http_svc = services.get("http")
    if http_svc is not None and http_svc.has_credentials():
        try:
            events = http_svc.get("/calendar/events")
            if events:
                return events
        except Exception as exc:  # noqa: BLE001
            # 服务异常时记录警告并降低置信度，避免静默回退到 mock 数据
            ctx["confidence"] = 0.3
            ctx.setdefault("_warnings", []).append(
                f"http 服务调用失败，回退到 mock 数据：{type(exc).__name__}: {exc}"
            )
    return list(_MOCK_SCHEDULE)


def _schedule_detect_conflicts(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """检测日程冲突（时间重叠）。"""
    events = ctx.get("events", [])
    # 按开始时间排序
    sorted_events = sorted(events, key=lambda e: e.get("start", ""))
    conflicts: list[dict[str, Any]] = []

    for i in range(len(sorted_events) - 1):
        curr = sorted_events[i]
        next_evt = sorted_events[i + 1]
        curr_end = curr.get("end", "")
        next_start = next_evt.get("start", "")
        # 简化冲突检测：当前事件结束时间晚于下一事件开始时间
        if curr_end and next_start and curr_end > next_start:
            conflicts.append({
                "event_a": curr.get("title", "?"),
                "event_b": next_evt.get("title", "?"),
                "overlap": f"{next_start} ~ {curr_end}",
            })

    # 设置置信度：有冲突时置信度取决于冲突数
    total = len(sorted_events)
    if total == 0:
        confidence = 1.0
    elif len(conflicts) == 0:
        confidence = 0.95
    else:
        confidence = max(0.4, 1.0 - len(conflicts) * 0.2)

    ctx["confidence"] = confidence
    return conflicts


def _schedule_suggestions(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """生成日程调整建议。"""
    conflicts = ctx.get("conflicts", [])
    events = ctx.get("events", [])
    suggestions: list[dict[str, Any]] = []

    for conflict in conflicts:
        suggestions.append({
            "type": "reschedule",
            "description": (
                f"「{conflict['event_a']}」与「{conflict['event_b']}」"
                f"时间重叠（{conflict['overlap']}），建议调整其中一个的时间"
            ),
        })

    if not conflicts and events:
        suggestions.append({
            "type": "info",
            "description": f"今日共 {len(events)} 项日程，无时间冲突",
        })

    return suggestions


# ====================================================================== #
# Mock 数据（dry_run 使用）
# ====================================================================== #

_MOCK_WEEKLY_COMMITS: list[dict[str, Any]] = [
    {"sha": "abc12345", "author": "alice", "message": "feat(auth): 支持 OAuth2 登录"},
    {"sha": "def67890", "author": "bob", "message": "fix(api): 修复分页 off-by-one 错误"},
    {"sha": "ghi13579", "author": "carol", "message": "feat!: 重构用户模型\n\nBREAKING CHANGE: 移除 deprecated 字段"},
    {"sha": "jkl24680", "author": "dave", "message": "docs: 更新 API 文档"},
    {"sha": "mno11223", "author": "eve", "message": "fix(upload): 修复大文件上传超时"},
]

_MOCK_EMAILS: list[dict[str, Any]] = [
    {
        "subject": "【紧急】生产环境故障，需立即处理",
        "from": "alert@system.com",
        "body": "生产环境 CPU 使用率超过 90%，请立即介入",
        "date": "2026-07-11T08:00:00Z",
    },
    {
        "subject": "周报：团队进度同步",
        "from": "pm@team.com",
        "body": "本周团队进度周报，请查阅",
        "date": "2026-07-11T09:00:00Z",
    },
    {
        "subject": "关于 API 设计的讨论",
        "from": "dev@team.com",
        "body": "想讨论一下新接口的设计方案，你看什么时候方便",
        "date": "2026-07-11T10:30:00Z",
    },
    {
        "subject": "订阅确认：技术周报",
        "from": "newsletter@tech.com",
        "body": "感谢订阅技术周报，每周一发送",
        "date": "2026-07-11T11:00:00Z",
    },
]

_MOCK_SCHEDULE: list[dict[str, Any]] = [
    {"title": "晨会", "start": "2026-07-11T09:00:00", "end": "2026-07-11T09:30:00"},
    {"title": "需求评审", "start": "2026-07-11T09:30:00", "end": "2026-07-11T10:30:00"},
    {"title": "1:1 沟通", "start": "2026-07-11T10:00:00", "end": "2026-07-11T10:30:00"},
    {"title": "午餐", "start": "2026-07-11T12:00:00", "end": "2026-07-11T13:00:00"},
    {"title": "代码评审", "start": "2026-07-11T14:00:00", "end": "2026-07-11T15:00:00"},
]
