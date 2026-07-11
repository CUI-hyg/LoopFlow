"""Token 预算追踪与降级。

Budget 控制 Loop 的 Token 消耗上限，参考 loop-engineering 的 loop-budget 机制：

- 花费达到 ``threshold``（默认 0.8）日上限时，触发降级（L2→L1，仅报告）。
- 花费达到日上限时，应停止循环。
- ``loop-pause-all`` 由 :class:`~loopkits.core.state.State` 处理，Budget 专注
  Token 维度。

配置文件 ``loop-budget.yaml`` 使用极简 YAML 子集（``key: value`` 平铺），无需
引入 PyYAML 依赖。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["Budget"]


class Budget(BaseModel):
    """Token 预算追踪器。

    Attributes:
        daily_cap: 每日 Token 上限。
        spent: 已花费 Token 数。
        threshold: 降级阈值（占 daily_cap 的比例，默认 0.8）。
        degraded: 是否已触发降级。
    """

    daily_cap: int = 100_000
    spent: int = 0
    threshold: float = 0.8
    degraded: bool = False

    # ------------------------------------------------------------------ #
    # 记录与查询
    # ------------------------------------------------------------------ #
    def record(self, usage: int) -> int:
        """记录一次 Token 消耗，返回累计已花费。

        若累计达到阈值则自动标记降级。
        """
        if usage < 0:
            raise ValueError("Token 消耗不能为负数")
        self.spent += usage
        if self.spent >= self._threshold_tokens():
            self.degraded = True
        return self.spent

    def is_degraded(self) -> bool:
        """是否已超过降级阈值（需要切换为 L1 仅报告模式）。"""
        return self.degraded or self.spent >= self._threshold_tokens()

    def should_stop(self) -> bool:
        """是否已完全耗尽日预算（应停止循环）。"""
        return self.spent >= self.daily_cap

    def remaining(self) -> int:
        """剩余 Token 预算。"""
        return max(0, self.daily_cap - self.spent)

    def ratio(self) -> float:
        """已花费占日上限的比例（0.0 ~ 1.0+）。"""
        if self.daily_cap <= 0:
            return 1.0
        return self.spent / self.daily_cap

    def degrade(self) -> "Budget":
        """手动触发降级（L2→L1）。返回自身以支持链式调用。"""
        self.degraded = True
        return self

    def reset(self) -> "Budget":
        """重置当日花费（跨天时调用）。"""
        self.spent = 0
        self.degraded = False
        return self

    def _threshold_tokens(self) -> int:
        """阈值对应的 Token 数。"""
        return int(self.daily_cap * self.threshold)

    # ------------------------------------------------------------------ #
    # loop-budget.yaml 读写（极简 YAML 子集：key: value 平铺）
    # ------------------------------------------------------------------ #
    def save(self, path: str | Path = "loop-budget.yaml") -> None:
        """写入 loop-budget.yaml（极简 YAML 格式）。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Loop Budget — 由 LoopKits 维护",
            f"daily_cap: {self.daily_cap}",
            f"spent: {self.spent}",
            f"threshold: {self.threshold}",
            f"degraded: {self.degraded}",
        ]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path = "loop-budget.yaml") -> "Budget":
        """从 loop-budget.yaml 加载预算配置；文件不存在则返回默认 Budget。"""
        p = Path(path)
        if not p.exists():
            return cls()
        data: dict[str, Any] = _parse_simple_yaml(p.read_text(encoding="utf-8"))
        # 仅取已知字段，类型转换
        fields: dict[str, Any] = {}
        if "daily_cap" in data:
            fields["daily_cap"] = int(data["daily_cap"])
        if "spent" in data:
            fields["spent"] = int(data["spent"])
        if "threshold" in data:
            fields["threshold"] = float(data["threshold"])
        if "degraded" in data:
            fields["degraded"] = _to_bool(data["degraded"])
        return cls(**fields)


def _parse_simple_yaml(text: str) -> dict[str, str]:
    """解析极简 YAML 子集：仅支持 ``key: value`` 平铺，忽略注释与空行。"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        result[key.strip()] = value.strip()
    return result


def _to_bool(value: str) -> bool:
    """将字符串转为布尔值。"""
    return value.lower() in {"true", "1", "yes", "on"}
