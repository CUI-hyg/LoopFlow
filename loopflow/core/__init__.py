"""LoopFlow 核心原语。

包含 LoopFlow 公式的四类一等原语及配套的数据/安全机制：

- :mod:`loopflow.core.loop` — Loop 自治循环原语
- :mod:`loopflow.core.workflow` — WorkFlow 有向图步骤串联
- :mod:`loopflow.core.agent` — Agent 基类与 Maker/Checker/Corrector/Verifier 四角色
- :mod:`loopflow.core.state` — 跨迭代状态持久化（STATE.md / JSON）
- :mod:`loopflow.core.budget` — Token 预算追踪与降级
- :mod:`loopflow.core.constraints` — 约束解析与路径/行为门控
- :mod:`loopflow.core.memory` — 跨迭代记忆（ratchet 棘轮机制）
"""

from loopflow.core.loop import Loop, LoopConfig, LoopResult, TrustLevel
from loopflow.core.workflow import WorkFlow, Step, RetryPolicy
from loopflow.core.agent import Agent, AgentRole, Maker, Checker, Corrector, Verifier
from loopflow.core.state import State
from loopflow.core.budget import Budget
from loopflow.core.constraints import Constraint, Constraints
from loopflow.core.memory import Memory

__all__ = [
    "Loop",
    "LoopConfig",
    "LoopResult",
    "TrustLevel",
    "WorkFlow",
    "Step",
    "RetryPolicy",
    "Agent",
    "AgentRole",
    "Maker",
    "Checker",
    "Corrector",
    "Verifier",
    "State",
    "Budget",
    "Constraint",
    "Constraints",
    "Memory",
]
