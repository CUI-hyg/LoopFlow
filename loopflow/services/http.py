"""通用 HTTP 服务连接器。

提供 GET / POST / PUT / DELETE 四个 REST 方法，使用标准库 ``urllib.request``
实现，适用于任意 REST API 集成场景。
"""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from loopflow.services.base import Service, ServiceConfig

__all__ = ["HTTPService"]

# 内网/保留地址网段黑名单（防止 SSRF 打内网与云元数据 169.254.169.254）
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),  # 链路本地（含云元数据）
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # IPv6 唯一本地
]


def _is_private_ip(ip_str: str) -> bool:
    """判断 IP 是否属于内网/保留地址。无法解析按危险处理。"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return any(ip in net for net in _PRIVATE_NETWORKS)


def _assert_safe_host(host: str) -> None:
    """校验主机名解析后的所有 IP 均不在内网黑名单中。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise urllib.error.URLError(f"主机名解析失败：{host}（{exc}）") from exc
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = sockaddr[0]
        if _is_private_ip(ip):
            raise urllib.error.URLError(
                f"SSRF 防护：主机 {host} 解析到内网地址 {ip}，已拦截"
            )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁用自动重定向，防止 SSRF 通过 30x 跳转到内网。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise urllib.error.HTTPError(newurl, code, msg, headers, fp)


class HTTPService(Service):
    """通用 REST API 连接器。

    Args:
        base_url: API 基址（如 ``https://api.example.com``）。
        headers: 默认请求头。
        auth_token: Bearer Token（自动添加到 ``Authorization`` 头）。
        name: 服务实例名称（用于注册表）。
    """

    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        auth_token: str = "",
        name: str = "http",
    ) -> None:
        creds: dict[str, Any] = {}
        if auth_token:
            creds["auth_token"] = auth_token
        if headers:
            creds["headers"] = headers
        config = ServiceConfig(
            name=name,
            service_type="http",
            credentials=creds,
            base_url=base_url.rstrip("/"),
            enabled=True,
        )
        super().__init__(config)
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers) if headers else {}
        self._auth_token = auth_token

    # ------------------------------------------------------------------ #
    # 内部：请求构造与发送
    # ------------------------------------------------------------------ #
    def _build_headers(self) -> dict[str, str]:
        """构造完整请求头。"""
        headers = dict(self._headers)
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送 HTTP 请求并解析 JSON 响应。

        Args:
            method: HTTP 方法（GET / POST / PUT / DELETE）。
            path: 请求路径（相对于 ``base_url``，或完整 URL）。
            params: URL 查询参数。
            body: 请求体（JSON）。

        Returns:
            解析后的 JSON 响应字典。无 JSON 响应体时返回空字典。

        Raises:
            urllib.error.HTTPError: HTTP 错误（非 2xx）。
            urllib.error.URLError: 网络错误。
        """
        # 构造完整 URL
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{self._base_url}/{path.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        # SSRF 防护：解析主机名并校验其 IP 不在内网黑名单中
        host = urllib.parse.urlsplit(url).hostname
        if host:
            _assert_safe_host(host)

        data = None
        headers = self._build_headers()
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        # 禁用自动重定向，防止通过 30x 跳转到内网地址
        opener = urllib.request.build_opener(_NoRedirectHandler)
        with opener.open(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}

    # ------------------------------------------------------------------ #
    # REST 方法
    # ------------------------------------------------------------------ #
    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 GET 请求。

        Args:
            path: 请求路径。
            params: URL 查询参数。

        Returns:
            JSON 响应字典。
        """
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 POST 请求。

        Args:
            path: 请求路径。
            body: JSON 请求体。

        Returns:
            JSON 响应字典。
        """
        return self._request("POST", path, body=body)

    def put(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 PUT 请求。

        Args:
            path: 请求路径。
            body: JSON 请求体。

        Returns:
            JSON 响应字典。
        """
        return self._request("PUT", path, body=body)

    def delete(self, path: str) -> dict[str, Any]:
        """发送 DELETE 请求。

        Args:
            path: 请求路径。

        Returns:
            JSON 响应字典。
        """
        return self._request("DELETE", path)

    # ------------------------------------------------------------------ #
    # 健康检查
    # ------------------------------------------------------------------ #
    def health_check(self) -> bool:
        """检查服务是否可用。

        对 ``base_url`` 发送 GET 请求，返回 2xx 即视为健康。
        无 ``base_url`` 时返回 False。
        """
        if not self._base_url:
            return False
        try:
            url = self._base_url
            req = urllib.request.Request(
                url, method="GET", headers=self._build_headers()
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            return False

    def has_credentials(self) -> bool:
        """是否有凭证（通用 HTTP 不强制要求凭证）。"""
        # HTTPService 的凭证是可选的（公开 API 无需 token）
        return True
