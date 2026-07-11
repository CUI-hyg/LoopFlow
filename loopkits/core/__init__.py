"""LoopKits 核心原语。

包含 LoopFlow 公式的四类一等原语及配套的数据/安全机制：

- :mod:`loopkits.core.loop` — Loop 自治循环原语
- :mod:`loopkits.core.workflow` — WorkFlow 有向图步骤串联
- :mod:`loopkits.core.agent` — Agent 基类与 Maker/Checker/Corrector/Verifier 四角色
- :mod:`loopkits.core.state` — 跨迭代状态持久化（STATE.md / JSON）
- :mod:`loopkits.core.budget` — Token 预算追踪与降级
- :mod:`loopkits.core.constraints` — 约束解析与路径/行为门控
- :mod:`loopkits.core.memory` — 跨迭代记忆（ratchet 棘轮机制）
"""

from loopkits.core.loop import Loop, LoopConfig, LoopResult, TrustLevel
from loopkits.core.workflow import WorkFlow, Step, RetryPolicy
from loopkits.core.agent import Agent, AgentRole, Maker, Checker, Corrector, Verifier
from loopkits.core.state import State
from loopkits.core.budget import Budget
from loopkits.core.constraints import Constraint, Constraints
from loopkits.core.memory import Memory

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
