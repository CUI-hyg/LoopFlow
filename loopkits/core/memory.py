"""跨迭代记忆（ratchet 棘轮机制）。

借鉴 karpathy/autoresearch 的核心思想：**只保留改进**。每次迭代产出结果与
标量指标，若新结果优于历史最佳则保留（advance），否则回滚（reset）。git
可作为持久化后端——``git commit`` 保留改进、``git reset`` 回滚退步。

标量指标驱动：

- ``direction="minimize"``：指标越小越好（如 val_bpb、错误率）
- ``direction="maximize"``：指标越大越好（如准确率、得分）
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["Memory", "MemoryEntry"]


class MemoryEntry(BaseModel):
    """单次迭代的记忆条目。

    Attributes:
        iteration: 迭代序号。
        result: 迭代产出（任意可序列化对象）。
        metric: 标量指标值（用于 ratchet 比较）。
        kept: 是否被保留（True=改进，False=回滚）。
        note: 备注。
    """

    iteration: int
    result: Any = None
    metric: float | None = None
    kept: bool = True
    note: str = ""


class Memory(BaseModel):
    """跨迭代记忆：ratchet 棘轮机制，只保留改进。

    Attributes:
        history: 历次迭代记录列表。
        best_metric: 历史最佳指标值。
        best_result: 历史最佳结果。
        best_iteration: 最佳结果对应的迭代序号。
        direction: 指标方向（``"minimize"`` 或 ``"maximize"``）。
        git_enabled: 是否启用 git 作为持久化后端。
        git_repo_path: git 仓库路径（git_enabled=True 时使用）。
    """

    history: list[MemoryEntry] = Field(default_factory=list)
    best_metric: float | None = None
    best_result: Any = None
    best_iteration: int | None = None
    direction: str = "minimize"
    git_enabled: bool = False
    git_repo_path: str = "."

    # ------------------------------------------------------------------ #
    # 记录与 ratchet
    # ------------------------------------------------------------------ #
    def record(
        self,
        iteration: int,
        result: Any = None,
        metric: float | None = None,
        note: str = "",
    ) -> MemoryEntry:
        """记录一次迭代结果，并执行 ratchet 判断。

        若 ``metric`` 优于 ``best_metric``（或首次记录），则保留（kept=True），
        可选 git commit；否则回滚（kept=False），可选 git reset。

        返回本次记忆条目。
        """
        is_better = self._is_better(metric)
        entry = MemoryEntry(
            iteration=iteration,
            result=result,
            metric=metric,
            kept=is_better,
            note=note,
        )
        self.history.append(entry)

        if is_better:
            # 棘轮前进：更新最佳
            self.best_metric = metric
            self.best_result = result
            self.best_iteration = iteration
            if self.git_enabled:
                self._git_commit(f"loopkits: iteration {iteration} improved (metric={metric})")
        else:
            # 棘轮回滚：不更新最佳，可选 git reset
            if self.git_enabled:
                self._git_reset()
        return entry

    def ratchet(self, metric: float) -> bool:
        """便捷方法：仅比较指标，返回是否应保留（True=改进）。

        不修改 history，仅用于外部判断。
        """
        return self._is_better(metric)

    def _is_better(self, metric: float | None) -> bool:
        """判断新指标是否优于历史最佳。"""
        if metric is None:
            return True  # 无指标时默认保留
        if self.best_metric is None:
            return True  # 首次记录
        if self.direction == "minimize":
            return metric < self.best_metric
        return metric > self.best_metric

    # ------------------------------------------------------------------ #
    # git 持久化后端
    # ------------------------------------------------------------------ #
    def _git_commit(self, message: str) -> bool:
        """在 git 仓库中提交当前改动（保留改进）。"""
        return _run_git(self.git_repo_path, ["add", "-A"]) and _run_git(
            self.git_repo_path, ["commit", "-m", message, "--allow-empty"]
        )

    def _git_reset(self) -> bool:
        """回滚到上一个提交（丢弃退步）。"""
        return _run_git(self.git_repo_path, ["reset", "--hard", "HEAD"])

    # ------------------------------------------------------------------ #
    # 文件持久化
    # ------------------------------------------------------------------ #
    def save(self, path: str | Path = "loop-memory.json") -> None:
        """将记忆持久化到 JSON 文件。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path = "loop-memory.json") -> "Memory":
        """从 JSON 文件加载记忆；文件不存在则返回空 Memory。"""
        p = Path(path)
        if not p.exists():
            return cls()
        return cls.model_validate_json(p.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ #
    # 便捷查询
    # ------------------------------------------------------------------ #
    def summary(self) -> str:
        """返回记忆摘要字符串。"""
        total = len(self.history)
        kept = sum(1 for e in self.history if e.kept)
        direction = "↓越小越好" if self.direction == "minimize" else "↑越大越好"
        return (
            f"迭代 {total} 次，保留 {kept} 次改进；"
            f"最佳指标={self.best_metric}（{direction}，iter {self.best_iteration}）"
        )


def _run_git(repo_path: str, args: list[str]) -> bool:
    """执行 git 命令，返回是否成功（不抛异常）。"""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False
