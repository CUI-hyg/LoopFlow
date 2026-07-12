"""Slack 服务连接器。

通过 Slack Web API 读写消息，使用标准库 ``urllib.request`` 实现。

无 token 时自动进入 ``dry_run`` 模式（返回空列表，不抛异常）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from loopflow.services.base import Service, ServiceConfig

__all__ = ["SlackService"]

# Slack Web API 基址
_SLACK_API = "https://slack.com/api"


class SlackService(Service):
    """Slack 服务连接器。

    Args:
        token: Slack Bot User OAuth Token（``xoxb-`` 开头）。为空则进入 dry_run。
        channel: 默认频道 ID 或名称。
        name: 服务实例名称（用于注册表）。
    """

    def __init__(
        self,
        token: str = "",
        channel: str = "",
        name: str = "slack",
    ) -> None:
        creds: dict[str, Any] = {}
        if token:
            creds["token"] = token
        if channel:
            creds["channel"] = channel
        config = ServiceConfig(
            name=name,
            service_type="slack",
            credentials=creds,
            base_url=_SLACK_API,
            enabled=True,
        )
        super().__init__(config)
        self._token = token
        self._channel = channel

    # ------------------------------------------------------------------ #
    # 凭证检测
    # ------------------------------------------------------------------ #
    def has_credentials(self) -> bool:
        """是否有凭证（token 是必需的，channel 非凭证）。"""
        return bool(self._token)

    # ------------------------------------------------------------------ #
    # 内部：HTTP 请求
    # ------------------------------------------------------------------ #
    def _post(self, api_method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """调用 Slack Web API（POST form-encoded）。

        Returns:
            Slack API 响应字典。``ok`` 字段指示成功与否。
        """
        url = f"{_SLACK_API}/{api_method}"
        data = urllib.parse.urlencode(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    # ------------------------------------------------------------------ #
    # 消息操作
    # ------------------------------------------------------------------ #
    def post_message(self, text: str, channel: str = "") -> dict[str, Any]:
        """发送消息到频道。

        Args:
            text: 消息文本。
            channel: 目标频道。为空则使用构造时指定的默认频道。

        Returns:
            Slack API 响应。dry_run 模式返回空字典。
        """
        if not self._token:
            return {}
        target = channel or self._channel
        if not target:
            return {}
        return self._post("chat.postMessage", {"channel": target, "text": text})

    def list_messages(self, limit: int = 20, channel: str = "") -> list[dict[str, Any]]:
        """列出频道最近的消息。

        Args:
            limit: 最多返回的消息数。
            channel: 目标频道。为空则使用默认频道。

        Returns:
            消息列表。dry_run 模式返回空列表。
        """
        if not self._token:
            return []
        target = channel or self._channel
        if not target:
            return []
        try:
            resp = self._post(
                "conversations.history", {"channel": target, "limit": limit}
            )
            if not resp.get("ok"):
                return []
            messages = resp.get("messages", [])
            return messages if isinstance(messages, list) else []
        except (urllib.error.URLError, urllib.error.HTTPError):
            return []

    # ------------------------------------------------------------------ #
    # 健康检查
    # ------------------------------------------------------------------ #
    def health_check(self) -> bool:
        """检查 Slack API 是否可用。

        调用 ``auth.test`` 验证 token 有效性。无 token 时返回 False。
        """
        if not self._token:
            return False
        try:
            resp = self._post("auth.test", {})
            return bool(resp.get("ok"))
        except (urllib.error.URLError, urllib.error.HTTPError):
            return False
