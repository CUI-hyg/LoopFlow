"""LoopFlow — Python 原生的 Loop Engineering 框架。

> LoopFlow = Loops × WorkFlows + Agents & Services

核心原语（:mod:`loopflow.core`）：

- :class:`Loop` — 自治循环（目标→执行→检查→改进→重复/停止）
- :class:`WorkFlow` — 有向图步骤串联
- :class:`Agent` — 执行单元（Maker/Checker/Corrector/Verifier 四角色）
- :class:`State` — 跨迭代状态持久化
- :class:`Budget` — Token 预算追踪
- :class:`Constraints` — 约束解析与安全门控
- :class:`Memory` — 跨迭代记忆（ratchet 棘轮机制）

快速开始::

    from loopflow import Loop, LoopConfig, TrustLevel

    loop = Loop(LoopConfig(goal="清理过期 Issue", level=TrustLevel.L1))
    result = loop.run()
    print(result.iterations, result.success)
"""

from loopflow.core.loop import Loop, LoopConfig, LoopResult, TrustLevel
from loopflow.core.workflow import WorkFlow, Step, RetryPolicy
from loopflow.core.agent import (
    Agent,
    AgentRole,
    Maker,
    Checker,
    Corrector,
    Verifier,
)
from loopflow.core.state import State
from loopflow.core.budget import Budget
from loopflow.core.constraints import Constraint, Constraints, ConstraintType
from loopflow.core.memory import Memory, MemoryEntry

__version__ = "0.1.0"

__all__ = [
    # Loop
    "Loop",
    "LoopConfig",
    "LoopResult",
    "TrustLevel",
    # WorkFlow
    "WorkFlow",
    "Step",
    "RetryPolicy",
    # Agent
    "Agent",
    "AgentRole",
    "Maker",
    "Checker",
    "Corrector",
    "Verifier",
    # 数据 / 安全原语
    "State",
    "Budget",
    "Constraint",
    "Constraints",
    "ConstraintType",
    "Memory",
    "MemoryEntry",
    "__version__",
]
