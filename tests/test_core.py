"""核心原语单元测试。

覆盖 Loop / WorkFlow / Agent / State / Budget / Constraints / Memory / Safety。
所有测试独立运行，不依赖外部服务或凭证；文件 IO 使用 tmp_path fixture。
"""

from __future__ import annotations

import pytest

from loopflow.core.agent import (
    AgentRole,
    CheckResult,
    Checker,
    Correction,
    Corrector,
    Maker,
    Verifier,
)
from loopflow.core.budget import Budget
from loopflow.core.constraints import Constraints
from loopflow.core.loop import Loop, LoopConfig, TrustLevel
from loopflow.core.memory import Memory
from loopflow.core.safety import (
    SafetyError,
    SafetyGate,
    SafetyLevel,
    TrustUpgrade,
)
from loopflow.core.state import State
from loopflow.core.workflow import RetryPolicy, Step, WorkFlow


# ====================================================================== #
# Loop
# ====================================================================== #
def test_loop_basic():
    """Loop 基本运行：目标达成、最大迭代、暂停。"""
    # 1. 目标达成
    config = LoopConfig(goal="完成测试", max_iterations=5, stop_condition="done")
    loop = Loop(
        config,
        execute_fn=lambda state: {"result": "done"},
        check_fn=lambda state, result: True,
    )
    result = loop.run()
    assert result.success is True
    assert "目标达成" in result.stop_reason
    assert result.iterations >= 1

    # 2. 最大迭代（未达成）
    config2 = LoopConfig(goal="永不达成", max_iterations=3)
    loop2 = Loop(
        config2,
        execute_fn=lambda state: {"result": "x"},
        check_fn=lambda state, result: False,
    )
    result2 = loop2.run()
    assert result2.success is False
    assert result2.iterations == 3
    assert "最大迭代" in result2.stop_reason

    # 3. 暂停标志 — 循环不启动
    config3 = LoopConfig(goal="暂停测试", max_iterations=5)
    state3 = State(goal="暂停测试")
    state3.mark_paused("test-pause")
    loop3 = Loop(config3, state=state3, execute_fn=lambda s: {})
    result3 = loop3.run()
    assert result3.success is False
    assert result3.iterations == 0
    assert "pause" in result3.stop_reason.lower() or "暂停" in result3.stop_reason


def test_loop_budget_degrade():
    """预算降级：超过阈值时自动从 L2 切 L1。"""
    budget = Budget(spent=800, daily_cap=1000, threshold=0.8)
    assert budget.is_degraded() is True

    config = LoopConfig(goal="降级测试", max_iterations=3, level=TrustLevel.L2)
    loop = Loop(
        config,
        budget=budget,
        execute_fn=lambda state: {"report": "ok"},
        check_fn=lambda state, result: True,
    )
    assert loop.config.level == TrustLevel.L2
    loop.run()
    # 降级后应为 L1
    assert loop.config.level == TrustLevel.L1


# ====================================================================== #
# WorkFlow
# ====================================================================== #
def test_workflow_sequential():
    """WorkFlow 顺序执行：步骤按序运行，上下文传递。"""
    order: list[str] = []

    def step1(ctx):
        order.append("step1")
        return "a"

    def step2(ctx):
        order.append("step2")
        assert ctx.get("step1_output") == "a"
        return "b"

    wf = WorkFlow(
        name="sequential-test",
        steps=[
            Step("s1", step1, outputs="step1_output"),
            Step("s2", step2, outputs="step2_output"),
        ],
    )
    result = wf.execute()
    assert result.success is True
    assert order == ["step1", "step2"]
    assert result.context["step1_output"] == "a"
    assert result.context["step2_output"] == "b"
    assert len(result.steps) == 2


def test_workflow_retry():
    """WorkFlow 重试：失败后按重试策略重试，最终成功。"""
    attempts: list[int] = []

    def flaky(ctx):
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("暂时失败")
        return "ok"

    step = Step(
        "flaky",
        flaky,
        retry_policy=RetryPolicy(max_retries=3, backoff=0.0),
    )
    result = step.execute({})
    assert result.success is True
    assert result.attempts == 3
    assert result.output == "ok"

    # 重试耗尽后失败
    attempts.clear()

    def always_fail(ctx):
        attempts.append(1)
        raise RuntimeError("永久失败")

    step2 = Step(
        "always-fail",
        always_fail,
        retry_policy=RetryPolicy(max_retries=2, backoff=0.0),
    )
    result2 = step2.execute({})
    assert result2.success is False
    assert result2.attempts == 3  # 1 + 2 retries
    assert "永久失败" in result2.error


# ====================================================================== #
# Agent 四角色
# ====================================================================== #
def test_agent_roles():
    """Agent 四角色：Maker / Checker / Corrector / Verifier。"""
    # Maker
    maker = Maker(name="m1", handler=lambda task: f"made: {task}")
    assert maker.role == AgentRole.MAKER
    assert maker.execute("feature") == "made: feature"

    # Checker
    checker = Checker(name="c1")
    result = checker.execute({"output": "hello world", "spec": "world"})
    assert isinstance(result, CheckResult)
    assert result.passed is True
    # 不符合规范
    result2 = checker.execute({"output": "hello", "spec": "world"})
    assert result2.passed is False
    assert len(result2.issues) > 0

    # Corrector
    corrector = Corrector(name="cor1", confidence_threshold=0.7)
    # 低置信度 → 暂停
    correction = corrector.execute({"confidence": 0.5, "candidates": ["A", "B"]})
    assert isinstance(correction, Correction)
    assert correction.paused is True
    assert "0.50" in correction.reason
    # 高置信度 → 继续
    correction2 = corrector.execute({"confidence": 0.9})
    assert correction2.paused is False

    # Verifier
    verifier = Verifier(name="v1")
    vresult = verifier.execute({"result": "目标已达成", "goal": "达成"})
    from loopflow.core.agent import VerifyResult
    assert isinstance(vresult, VerifyResult)
    assert vresult.achieved is True


# ====================================================================== #
# State
# ====================================================================== #
def test_state_persistence(tmp_path):
    """State 持久化：save / load 往返一致。"""
    state = State(goal="持久化测试", iteration=5, todos=["任务A", "任务B"])
    state.completed.append("已完成项")
    state.notes = "测试备注"

    state_path = tmp_path / "STATE.md"
    state.save(state_path)

    # MD 和 JSON 都应生成
    assert state_path.exists()
    assert (tmp_path / "STATE.json").exists()

    # 从 JSON 加载（优先）
    loaded = State.load(state_path)
    assert loaded.goal == "持久化测试"
    assert loaded.iteration == 5
    assert loaded.todos == ["任务A", "任务B"]
    assert loaded.completed == ["已完成项"]
    assert loaded.notes == "测试备注"


def test_state_pause():
    """State 暂停标志：mark_paused / clear_paused / is_paused。"""
    state = State(goal="暂停测试")
    assert state.is_paused() is False

    state.mark_paused("紧急维护")
    assert state.is_paused() is True
    assert "紧急维护" in state.notes

    state.clear_paused()
    assert state.is_paused() is False
    assert state.notes == ""


# ====================================================================== #
# Budget
# ====================================================================== #
def test_budget_threshold():
    """Budget 阈值检查：80% 降级、100% 停止。"""
    b = Budget(daily_cap=1000, threshold=0.8)
    assert b.is_degraded() is False
    assert b.should_stop() is False

    b.record(799)
    assert b.is_degraded() is False
    assert b.remaining() == 201

    b.record(1)  # 800，达阈值
    assert b.is_degraded() is True
    assert b.should_stop() is False

    b.record(200)  # 1000，耗尽
    assert b.should_stop() is True
    assert b.remaining() == 0
    assert b.ratio() == 1.0

    # reset
    b.reset()
    assert b.spent == 0
    assert b.degraded is False


# ====================================================================== #
# Constraints
# ====================================================================== #
def test_constraints_path():
    """Constraints 路径保护：敏感路径禁止、正常路径允许。"""
    c = Constraints()

    # 敏感路径禁止
    assert c.check_path(".env") is False
    assert c.check_path(".env.local") is False
    assert c.check_path(".env.production") is False
    assert c.check_path("secrets/key.pem") is False
    assert c.check_path("credentials/api.json") is False
    assert c.check_path("auth/login.py") is False
    assert c.check_path("payments/billing.py") is False
    assert c.check_path("billing/invoice.py") is False
    assert c.check_path(".terraform/main.tf") is False
    assert c.check_path("k8s/production/deploy.yaml") is False
    assert c.check_path("loop-budget.yaml") is False
    assert c.check_path("loop-constraints.md") is False

    # 正常路径允许
    assert c.check_path("src/main.py") is True
    assert c.check_path("README.md") is True
    assert c.check_path("tests/test_core.py") is True

    # 白名单覆盖黑名单
    c.add_path_allow(".env")
    assert c.check_path(".env") is True


def test_constraints_action():
    """Constraints 行为门控：禁止自动合并/关闭Issue/禁用测试。"""
    c = Constraints()

    # 禁止的行为
    assert c.check_action("auto-merge-main") is False
    assert c.check_action("close-issue") is False
    assert c.check_action("disable-tests") is False

    # 允许的行为
    assert c.check_action("commit-code") is True
    assert c.check_action("run-tests") is True
    assert c.check_action("create-branch") is True

    # 违规记录
    c.check_action("auto-merge-main")
    assert len(c.violations_list()) > 0


# ====================================================================== #
# Memory ratchet
# ====================================================================== #
def test_memory_ratchet():
    """Memory ratchet：只保留改进（minimize 和 maximize）。"""
    # minimize：指标越小越好
    m = Memory(direction="minimize")
    e1 = m.record(iteration=1, result="v1", metric=5.0)
    assert e1.kept is True  # 首次记录
    assert m.best_metric == 5.0

    e2 = m.record(iteration=2, result="v2", metric=3.0)
    assert e2.kept is True  # 3 < 5，改进
    assert m.best_metric == 3.0
    assert m.best_iteration == 2

    e3 = m.record(iteration=3, result="v3", metric=4.0)
    assert e3.kept is False  # 4 > 3，退步
    assert m.best_metric == 3.0  # 最佳不变

    # maximize：指标越大越好
    m2 = Memory(direction="maximize")
    e1 = m2.record(iteration=1, result="v1", metric=3.0)
    assert e1.kept is True
    assert m2.best_metric == 3.0

    e2 = m2.record(iteration=2, result="v2", metric=5.0)
    assert e2.kept is True  # 5 > 3，改进
    assert m2.best_metric == 5.0

    e3 = m2.record(iteration=3, result="v3", metric=4.0)
    assert e3.kept is False  # 4 < 5，退步
    assert m2.best_metric == 5.0


# ====================================================================== #
# SafetyGate
# ====================================================================== #
def test_safety_gate():
    """SafetyGate 统一检查：路径/预算/worktree/pause。"""
    gate = SafetyGate()

    # check_path
    assert gate.check_path(".env") is False
    assert gate.check_path("src/main.py") is True
    # 带自定义 constraints
    cs = Constraints()
    assert gate.check_path("secrets/key.pem", cs) is False

    # check_budget
    assert gate.check_budget(Budget(spent=100, daily_cap=1000)) == SafetyLevel.OK
    assert gate.check_budget(Budget(spent=800, daily_cap=1000)) == SafetyLevel.DEGRADED
    assert gate.check_budget(Budget(spent=1000, daily_cap=1000)) == SafetyLevel.STOPPED

    # require_worktree
    with pytest.raises(SafetyError):
        gate.require_worktree("src/main.py", is_unattended=True, in_worktree=False)
    # 在 worktree 中 → 不抛
    gate.require_worktree("src/main.py", is_unattended=True, in_worktree=True)
    # 有人值守 → 不抛
    gate.require_worktree("src/main.py", is_unattended=False, in_worktree=False)

    # check_pause
    s = State()
    assert gate.check_pause(s) is False
    s.mark_paused()
    assert gate.check_pause(s) is True

    # full_check — 暂停优先
    paused_state = State()
    paused_state.mark_paused()
    assert gate.full_check(state=paused_state) == SafetyLevel.STOPPED

    # full_check — 预算降级
    assert gate.full_check(budget=Budget(spent=850, daily_cap=1000)) == SafetyLevel.DEGRADED

    # full_check — 路径黑名单抛异常
    with pytest.raises(SafetyError):
        gate.full_check(path=".env", constraints=Constraints())

    # full_check — 正常
    assert gate.full_check(
        path="src/main.py",
        constraints=Constraints(),
        budget=Budget(spent=100, daily_cap=1000),
    ) == SafetyLevel.OK


# ====================================================================== #
# TrustUpgrade
# ====================================================================== #
def test_trust_upgrade():
    """信任级别升级路径：L1→L2→L3，需 N 次成功且无失败。"""
    tu = TrustUpgrade(min_success=3)

    # 升级路径
    assert tu.upgrade_path(TrustLevel.L1) == [TrustLevel.L2, TrustLevel.L3]
    assert tu.upgrade_path(TrustLevel.L2) == [TrustLevel.L3]
    assert tu.upgrade_path(TrustLevel.L3) == []

    # 初始不可升级（0 次成功）
    assert tu.can_upgrade(TrustLevel.L1, TrustLevel.L2) is False
    # 跨级不可升级
    assert tu.can_upgrade(TrustLevel.L1, TrustLevel.L3) is False

    # 记录 2 次成功 — 仍不够
    tu.record_run(TrustLevel.L1, True)
    tu.record_run(TrustLevel.L1, True)
    assert tu.can_upgrade(TrustLevel.L1, TrustLevel.L2) is False

    # 第 3 次成功 — 可升级
    tu.record_run(TrustLevel.L1, True)
    assert tu.can_upgrade(TrustLevel.L1, TrustLevel.L2) is True
    assert tu.suggest_level() == TrustLevel.L2

    # 出现失败 — 不可升级
    tu.record_run(TrustLevel.L1, False)
    assert tu.can_upgrade(TrustLevel.L1, TrustLevel.L2) is False
    assert tu.suggest_level() == TrustLevel.L1

    # 升级到 L2 后，L2→L3 同样需要 3 次成功
    tu.reset()
    tu.set_current_level(TrustLevel.L2)
    for _ in range(3):
        tu.record_run(TrustLevel.L2, True)
    assert tu.can_upgrade(TrustLevel.L2, TrustLevel.L3) is True
    assert tu.suggest_level() == TrustLevel.L3
