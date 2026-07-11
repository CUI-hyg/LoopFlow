"""GitHub 服务连接器。

通过 GitHub REST API 读写 Issue / PR，使用标准库 ``urllib.request`` 实现，
不引入 ``PyGithub`` 等额外依赖。

无 token 时自动进入 ``dry_run`` 模式（返回空列表，不抛异常）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from loopkits.services.base import Service, ServiceConfig

__all__ = ["GitHubService"]

# GitHub REST API 基址
_GITHUB_API = "https://api.github.com"


class GitHubService(Service):
    """GitHub 服务连接器。

    Args:
        token: GitHub Personal Access Token。为空则进入 dry_run 模式。
        repo: 仓库全名（``owner/repo``），为空则无法读写具体仓库数据。
        name: 服务实例名称（用于注册表）。
    """

    def __init__(
        self,
        token: str = "",
        repo: str = "",
        name: str = "github",
    ) -> None:
        creds: dict[str, Any] = {}
        if token:
            creds["token"] = token
        if repo:
            creds["repo"] = repo
        config = ServiceConfig(
            name=name,
            service_type="github",
            credentials=creds,
            base_url=_GITHUB_API,
            enabled=True,
        )
        super().__init__(config)
        self._token = token
        self._repo = repo.strip().strip("/")

    # ------------------------------------------------------------------ #
    # 凭证检测
    # ------------------------------------------------------------------ #
    def has_credentials(self) -> bool:
        """是否有凭证（token 是必需的，repo 非凭证）。"""
        return bool(self._token)

    # ------------------------------------------------------------------ #
    # 内部：HTTP 请求
    # ------------------------------------------------------------------ #
    def _headers(self) -> dict[str, str]:
        """构造请求头。"""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """发送 HTTP 请求并解析 JSON 响应。

        Raises:
            ValueError: 未配置 repo 但请求需要仓库信息。
            urllib.error.HTTPError: HTTP 错误。
        """
        url = f"{_GITHUB_API}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method=method, headers=self._headers()
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)

    # ------------------------------------------------------------------ #
    # Issue 操作
    # ------------------------------------------------------------------ #
    def list_issues(self, state: str = "open") -> list[dict[str, Any]]:
        """列出当前仓库的 Issue。

        Args:
            state: ``open`` / ``closed`` / ``all``。

        Returns:
            Issue 列表。无 token 或无 repo 时返回空列表（dry_run）。
        """
        if not self._token or not self._repo:
            return []
        try:
            result = self._request(
                "GET", f"/repos/{self._repo}/issues?state={state}"
            )
            return result if isinstance(result, list) else []
        except (urllib.error.URLError, urllib.error.HTTPError):
            return []

    def get_issue(self, number: int) -> dict[str, Any]:
        """获取指定编号的 Issue。

        无 token 或无 repo 时返回空字典（dry_run）。
        """
        if not self._token or not self._repo:
            return {}
        try:
            result = self._request("GET", f"/repos/{self._repo}/issues/{number}")
            return result if isinstance(result, dict) else {}
        except (urllib.error.URLError, urllib.error.HTTPError):
            return {}

    def add_label(self, number: int, labels: list[str]) -> dict[str, Any]:
        """为 Issue 添加标签。

        Returns:
            GitHub API 响应。dry_run 模式返回空字典。
        """
        if not self._token or not self._repo:
            return {}
        return self._request(
            "POST",
            f"/repos/{self._repo}/issues/{number}/labels",
            body={"labels": labels},
        )

    def create_comment(self, number: int, body: str) -> dict[str, Any]:
        """在 Issue 下创建评论。

        Returns:
            GitHub API 响应。dry_run 模式返回空字典。
        """
        if not self._token or not self._repo:
            return {}
        return self._request(
            "POST",
            f"/repos/{self._repo}/issues/{number}/comments",
            body={"body": body},
        )

    # ------------------------------------------------------------------ #
    # PR 操作
    # ------------------------------------------------------------------ #
    def list_prs(self, state: str = "open") -> list[dict[str, Any]]:
        """列出当前仓库的 Pull Request。

        Args:
            state: ``open`` / ``closed`` / ``all``。

        Returns:
            PR 列表。dry_run 模式返回空列表。
        """
        if not self._token or not self._repo:
            return []
        try:
            result = self._request(
                "GET", f"/repos/{self._repo}/pulls?state={state}"
            )
            return result if isinstance(result, list) else []
        except (urllib.error.URLError, urllib.error.HTTPError):
            return []

    # ------------------------------------------------------------------ #
    # 健康检查
    # ------------------------------------------------------------------ #
    def health_check(self) -> bool:
        """检查 GitHub API 是否可用。

        调用 ``/rate_limit`` 验证 token 有效性。无 token 时返回 False。
        """
        if not self._token:
            return False
        try:
            self._request("GET", "/rate_limit")
            return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            return False
