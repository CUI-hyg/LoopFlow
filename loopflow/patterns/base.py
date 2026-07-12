"""循环模式基类（Code 模式）。

每个 Pattern 描述一种可复用的 Loop Engineering 循环模式（如 daily-triage、
pr-babysitter 等）。模式通过 ``service_provider``（dict[str, Any]）抽象外部
服务依赖（GitHub / Slack / 邮件等），不硬编码任何真实 API 调用——这使得
``dry_run()`` 可在无凭证环境下运行，而真实运行时注入对应 services 即可。

设计要点：

- :class:`PatternMeta` 描述模式的元数据（名称、描述、默认信任级别、节奏、标签）。
- :class:`Pattern` 是 ABC，子类需实现 :meth:`build_loop` / :meth:`build_workflow`
  / :meth:`_execute` / :meth:`to_skill_md`。
- :meth:`dry_run` 在基类中提供通用实现：通过 ``_force_mock`` 标志强制走 mock
  数据路径，调用子类的 :meth:`_execute` 返回模拟结果。
- :meth:`validate` 提供默认校验（检查 meta 完整性），子类可扩展。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from loopflow.core.budget import Budget
from loopflow.core.constraints import Constraints
from loopflow.core.loop import Loop, LoopConfig, TrustLevel
from loopflow.core.memory import Memory
from loopflow.core.state import State
from loopflow.core.workflow import WorkFlow

__all__ = ["PatternMeta", "Pattern"]


class PatternMeta(BaseModel):
    """循环模式元数据。

    Attributes:
        name: 模式唯一标识（kebab-case，如 ``daily-triage``）。
        description: 一句话描述模式职责。
        default_level: 默认信任级别（L1 仅报告 / L2 辅助修复 / L3 全自动）。
        cadence: 节奏描述（如 ``1d`` / ``10m`` / ``6h``）。
        tags: 标签列表（用于检索与分类）。
    """

    name: str
    description: str
    default_level: TrustLevel = TrustLevel.L1
    cadence: str = ""
    tags: list[str] = Field(default_factory=list)


class Pattern(ABC):
    """循环模式抽象基类。

    子类通过实现 :meth:`_execute` 提供核心执行逻辑，并通过 ``service_provider``
    抽象外部服务。``dry_run()`` 无需凭证即可运行（使用 mock 数据）。

    Args:
        service_provider: 服务提供者字典，键为服务名（如 ``github`` / ``git``），
            值为服务对象。为空时 :meth:`_service` 返回 None，子类应回退到 mock 数据。
        level: 信任级别覆盖；为 None 则使用 ``meta.default_level``。
    """

    meta: PatternMeta

    def __init__(
        self,
        service_provider: dict[str, Any] | None = None,
        level: TrustLevel | None = None,
    ) -> None:
        self.service_provider: dict[str, Any] = service_provider or {}
        self._level_override: TrustLevel | None = level
        # dry_run 时置 True，使 _service 始终返回 None，强制走 mock 路径
        self._force_mock: bool = False

    # ------------------------------------------------------------------ #
    # 服务访问与信任级别
    # ------------------------------------------------------------------ #
    @property
    def effective_level(self) -> TrustLevel:
        """当前生效的信任级别（覆盖值优先，否则取 meta.default_level）。"""
        return self._level_override or self.meta.default_level

    def _service(self, name: str) -> Any | None:
        """按名获取服务对象。

        dry_run 模式下始终返回 None，确保不触碰真实服务。
        """
        if self._force_mock:
            return None
        return self.service_provider.get(name)

    def has_service(self, name: str) -> bool:
        """是否注入了指定服务（dry_run 时始终返回 False）。"""
        if self._force_mock:
            return False
        return name in self.service_provider

    # ------------------------------------------------------------------ #
    # 抽象方法：子类必须实现
    # ------------------------------------------------------------------ #
    @abstractmethod
    def build_loop(self, config_overrides: dict[str, Any] | None = None) -> Loop:
        """基于模式构建一个 :class:`Loop` 实例。

        Args:
            config_overrides: 配置覆盖项（如 ``max_iterations`` / ``goal``）。

        Returns:
            配置好 execute_fn / check_fn 的 Loop。
        """

    @abstractmethod
    def build_workflow(self, **kwargs: Any) -> WorkFlow:
        """构建该模式对应的 :class:`WorkFlow`（多步骤串联）。"""

    @abstractmethod
    def _execute(self, state: State) -> dict[str, Any]:
        """核心执行逻辑（作为 Loop 的 execute_fn）。

        子类应优先使用 :meth:`_service` 获取真实服务；服务缺失时回退到 mock
        数据，保证无凭证环境下也能运行。
        """

    @abstractmethod
    def to_skill_md(self) -> str:
        """生成该模式的 SKILL.md 内容片段（触发条件、步骤、验证）。"""

    # ------------------------------------------------------------------ #
    # 通用实现：dry_run / validate
    # ------------------------------------------------------------------ #
    def dry_run(self) -> dict[str, Any]:
        """模拟运行：不执行实际操作，返回 mock 结果。

        通过 ``_force_mock`` 标志使 :meth:`_service` 返回 None，子类的
        :meth:`_execute` 会回退到 mock 数据路径。
        """
        self._force_mock = True
        try:
            state = State(goal=self.meta.description, iteration=1)
            result = self._execute(state)
        finally:
            self._force_mock = False
        # 附加模式元信息，便于消费方识别
        result.setdefault("pattern", self.meta.name)
        result.setdefault("level", self.effective_level.value)
        result.setdefault("dry_run", True)
        return result

    def validate(self) -> list[str]:
        """校验模式配置，返回问题列表（空列表表示通过）。"""
        issues: list[str] = []
        if not self.meta.name:
            issues.append("meta.name 不能为空")
        if not self.meta.description:
            issues.append("meta.description 不能为空")
        if self.meta.default_level == TrustLevel.L3 and not self.meta.tags:
            issues.append("L3 全自动模式应至少有一个 tag 以便追溯")
        return issues

    # ------------------------------------------------------------------ #
    # 辅助方法：子类可直接复用
    # ------------------------------------------------------------------ #
    def _make_loop_config(
        self, config_overrides: dict[str, Any] | None = None
    ) -> LoopConfig:
        """基于 meta 与覆盖项构造 :class:`LoopConfig`。"""
        overrides = config_overrides or {}
        level = overrides.get("level", self.effective_level)
        if isinstance(level, str):
            level = TrustLevel(level)
        config = LoopConfig(
            goal=overrides.get("goal", self.meta.description),
            max_iterations=overrides.get("max_iterations", 1),
            level=level,
        )
        if "stop_condition" in overrides:
            config.stop_condition = overrides["stop_condition"]
        return config

    def _make_loop(
        self,
        config_overrides: dict[str, Any] | None = None,
        check_fn: Any | None = None,
    ) -> Loop:
        """通用 Loop 构造器：execute_fn 绑定 self._execute。

        子类的 :meth:`build_loop` 可直接调用此方法，或自行构造以获得更细粒度控制。
        """
        config = self._make_loop_config(config_overrides)
        # 默认 check：根据 stop_condition 判断
        # 无 stop_condition 时返回 False，让循环跑满 max_iterations（fail-safe）
        if check_fn is None:
            def _default_check(state: State, result: Any) -> bool:
                if not config.stop_condition:
                    return False
                # 有 stop_condition 时，单次执行后即视为达成
                return True
            check_fn = _default_check
        return Loop(
            config=config,
            execute_fn=self._execute,
            check_fn=check_fn,
        )

    def _default_constraints(self) -> Constraints:
        """返回默认约束集合（路径黑名单 + 行为门控）。"""
        return Constraints()

    def _default_budget(self) -> Budget:
        """返回默认预算。"""
        return Budget()

    def _default_memory(self) -> Memory:
        """返回默认记忆。"""
        return Memory()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.meta.name!r} level={self.effective_level.value}>"
