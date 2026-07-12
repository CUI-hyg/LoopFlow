"""状态持久化。

State 是 Loop 跨迭代记忆的「外部存储」：每次迭代结束后将当前进度写入
``STATE.md``（人可读 Markdown）与同名 ``.json``（结构化状态），下次迭代启动
时重新加载。参考 loop-engineering 的 STATE.md 模板。

支持 ``loop-pause-all`` 杀停开关：当该标志为真时，所有 Loop 应立即退出。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from pydantic import BaseModel, Field

__all__ = ["State"]


class State(BaseModel):
    """循环状态：跨迭代持久化的工作进度。

    Attributes:
        iteration: 当前迭代序号（从 0 开始）。
        goal: 当前循环的目标描述。
        todos: 待办事项列表（字符串）。
        completed: 已完成事项列表。
        history: 历次迭代的记录（每条为 dict）。
        paused: 是否处于暂停状态（对应 loop-pause-all）。
        last_run: 上次运行时间戳。
        notes: 自由备注（对应 STATE.md 的 Watch List 等）。
    """

    iteration: int = 0
    goal: str = ""
    todos: list[str] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
    paused: bool = False
    last_run: str = ""
    notes: str = ""

    # ------------------------------------------------------------------ #
    # 更新与持久化
    # ------------------------------------------------------------------ #
    def update(self, **changes) -> "State":
        """更新状态字段并记录一次迭代历史，随后返回自身以支持链式调用。

        传入 ``iteration`` / ``goal`` 等任意字段；未传入 ``last_run`` 时自动
        打上当前时间戳。
        """
        if "last_run" not in changes:
            changes["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # 把本次更新记入历史（便于回溯）
        record = {"iteration": self.iteration, **changes}
        self.history.append(record)
        for key, value in changes.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self

    def mark_paused(self, reason: str = "loop-pause-all") -> "State":
        """触发 loop-pause-all 杀停开关。"""
        self.paused = True
        self.notes = f"PAUSED: {reason}"
        return self

    def clear_paused(self) -> "State":
        """清除暂停标志（人工恢复）。"""
        self.paused = False
        self.notes = ""
        return self

    # ------------------------------------------------------------------ #
    # STATE.md / JSON 读写
    # ------------------------------------------------------------------ #
    def save(self, path: str | Path) -> None:
        """持久化到 STATE.md（人可读）与 STATE.json（结构化）。

        ``path`` 可指向 ``STATE.md`` 或 ``STATE.json``，两者都会基于同一
        stem 写出。若设置了环境变量 ``LOOPKITS_STATE_SECRET``，会额外写入
        HMAC-SHA256 签名文件 ``.sig`` 用于完整性校验，并将文件权限设为
        ``0o600``（仅所有者可读写）。
        """
        p = Path(path)
        md_path = p.with_suffix(".md")
        json_path = p.with_suffix(".json")
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        json_content = self.model_dump_json(indent=2)
        json_path.write_text(json_content, encoding="utf-8")
        # 设置结构化状态文件权限为仅所有者可读写
        try:
            os.chmod(json_path, 0o600)
        except OSError:
            pass
        # 完整性签名（若配置了 secret）
        secret = os.environ.get("LOOPKITS_STATE_SECRET")
        if secret:
            sig = hmac.new(
                secret.encode("utf-8"),
                json_content.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            sig_path = json_path.with_suffix(".sig")
            sig_path.write_text(sig, encoding="utf-8")
            try:
                os.chmod(sig_path, 0o600)
            except OSError:
                pass

    @classmethod
    def load(cls, path: str | Path) -> "State":
        """从文件加载状态：优先读 JSON（结构化），不存在则从 STATE.md 解析。

        若文件不存在则返回空 State。若设置了环境变量
        ``LOOPKITS_STATE_SECRET``，会校验 ``.sig`` 签名文件，签名缺失或不
        匹配时抛 :class:`ValueError`，防止状态文件被篡改。
        """
        p = Path(path)
        json_path = p.with_suffix(".json")
        if json_path.exists():
            json_content = json_path.read_text(encoding="utf-8")
            # 完整性校验（若配置了 secret）
            secret = os.environ.get("LOOPKITS_STATE_SECRET")
            if secret:
                sig_path = json_path.with_suffix(".sig")
                if not sig_path.exists():
                    raise ValueError("状态文件签名缺失，可能被篡改")
                expected = hmac.new(
                    secret.encode("utf-8"),
                    json_content.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                actual = sig_path.read_text(encoding="utf-8").strip()
                if not hmac.compare_digest(expected, actual):
                    raise ValueError("状态文件签名校验失败，可能被篡改")
            return cls.model_validate_json(json_content)
        md_path = p.with_suffix(".md")
        if md_path.exists():
            return cls.from_markdown(md_path.read_text(encoding="utf-8"))
        return cls()

    # ------------------------------------------------------------------ #
    # Markdown 序列化（人可读，对标 loop-engineering STATE.md 模板）
    # ------------------------------------------------------------------ #
    def to_markdown(self) -> str:
        """渲染为人可读的 STATE.md 文本。"""
        lines = [
            "# Loop State",
            "",
            f"Last run: {self.last_run or '(未运行)'}",
            "",
        ]
        if self.paused:
            lines.append("> ⏸ **PAUSED** — loop-pause-all 已激活，循环将立即退出。")
            lines.append("")
        lines.append(f"## Current Iteration: {self.iteration}")
        lines.append("")
        lines.append(f"**Goal**: {self.goal or '(未设置)'}")
        lines.append("")
        lines.append("## High Priority (loop is acting or waiting on human)")
        lines.append("")
        for item in self.todos:
            lines.append(f"- [ ] {item}")
        if not self.todos:
            lines.append("—")
        lines.append("")
        lines.append("## Completed")
        lines.append("")
        for item in self.completed:
            lines.append(f"- [x] {item}")
        if not self.completed:
            lines.append("—")
        lines.append("")
        lines.append("## History")
        lines.append("")
        for rec in self.history[-10:]:  # 仅保留最近 10 条，避免膨胀
            lines.append(f"- iter {rec.get('iteration', '?')}: {rec}")
        lines.append("")
        if self.notes:
            lines.append("## Notes")
            lines.append("")
            lines.append(self.notes)
            lines.append("")
        lines.append("---")
        lines.append("Run log: 由 LoopKits 自动维护。")
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str) -> "State":
        """从 STATE.md 文本解析状态（宽松解析，仅提取关键字段）。

        JSON 不可用时回退到此方法；解析失败的字段使用默认值。
        """
        state = cls()
        paused = "PAUSED" in text and "loop-pause-all" in text.lower()
        state.paused = paused
        # 解析 Last run
        for line in text.splitlines():
            if line.startswith("Last run:"):
                state.last_run = line.split(":", 1)[1].strip()
                break
        # 解析 Current Iteration
        for line in text.splitlines():
            if "Current Iteration:" in line:
                try:
                    state.iteration = int(
                        line.split("Current Iteration:", 1)[1].strip()
                    )
                except ValueError:
                    pass
                break
        # 解析 todos（- [ ] 开头）
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- [ ] "):
                state.todos.append(stripped[6:])
            elif stripped.startswith("- [x] "):
                state.completed.append(stripped[6:])
        return state

    # ------------------------------------------------------------------ #
    # 便捷查询
    # ------------------------------------------------------------------ #
    def is_paused(self) -> bool:
        """是否处于 loop-pause-all 暂停状态。"""
        return self.paused

    def next_iteration(self) -> int:
        """推进迭代序号并返回新值。"""
        self.iteration += 1
        return self.iteration
