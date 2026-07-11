"""IMA 知识库服务连接器。

复用 ``ima-skills`` 的 ``ima_api.cjs`` 脚本（Node.js）调用 IMA OpenAPI，
通过 ``subprocess`` 运行 ``node`` 实现，不引入 Python 侧额外依赖。

凭证从环境变量读取（优先 ``ima_client_id`` / ``ima_api_key``，其次
``IMA_OPENAPI_CLIENTID`` / ``IMA_OPENAPI_APIKEY``）。无凭证时进入 dry_run 模式。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loopkits.services.base import Service, ServiceConfig

__all__ = ["IMAService"]

# ima_api.cjs 脚本路径
_IMA_SCRIPT = Path("/data/user/skills/ima-skills-1.1.7/ima_api.cjs")

# IMA OpenAPI 基址
_IMA_BASE_URL = "https://ima.qq.com"


class IMAService(Service):
    """IMA 知识库服务连接器。

    通过调用 ``ima_api.cjs`` 脚本实现知识库搜索与浏览。

    Args:
        name: 服务实例名称（用于注册表）。
        script_path: ``ima_api.cjs`` 脚本路径（默认使用内置路径）。
    """

    def __init__(
        self,
        name: str = "ima",
        script_path: str | Path | None = None,
    ) -> None:
        # 从环境变量读取凭证
        client_id = (
            os.environ.get("ima_client_id")
            or os.environ.get("IMA_CLIENT_ID")
            or os.environ.get("IMA_OPENAPI_CLIENTID")
            or ""
        )
        api_key = (
            os.environ.get("ima_api_key")
            or os.environ.get("IMA_API_KEY")
            or os.environ.get("IMA_OPENAPI_APIKEY")
            or ""
        )
        creds: dict[str, Any] = {}
        if client_id:
            creds["client_id"] = client_id
        if api_key:
            creds["api_key"] = api_key
        config = ServiceConfig(
            name=name,
            service_type="ima",
            credentials=creds,
            base_url=_IMA_BASE_URL,
            enabled=True,
        )
        super().__init__(config)
        self._client_id = client_id
        self._api_key = api_key
        self._script_path = Path(script_path) if script_path else _IMA_SCRIPT

    # ------------------------------------------------------------------ #
    # 凭证检测
    # ------------------------------------------------------------------ #
    def has_credentials(self) -> bool:
        """是否有 IMA 凭证（client_id 与 api_key 均需存在）。"""
        return bool(self._client_id and self._api_key)

    # ------------------------------------------------------------------ #
    # 内部：调用 ima_api.cjs
    # ------------------------------------------------------------------ #
    def _call_api(
        self,
        api_path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """通过 subprocess 调用 ``ima_api.cjs`` 脚本。

        Args:
            api_path: IMA OpenAPI 路径（如 ``openapi/wiki/v1/search_knowledge_base``）。
            body: 请求体（将被序列化为 JSON 字符串传给脚本）。

        Returns:
            IMA API 响应字典。

        Raises:
            RuntimeError: 脚本执行失败或凭证缺失。
        """
        if not self.has_credentials():
            raise RuntimeError("IMA 凭证缺失，请设置 ima_client_id 和 ima_api_key 环境变量")
        if not self._script_path.exists():
            raise RuntimeError(f"IMA 脚本不存在：{self._script_path}")

        raw_body = json.dumps(body or {}, ensure_ascii=False)
        # 通过 options 传入凭证（避免依赖环境变量大小写）
        options = json.dumps(
            {"clientId": self._client_id, "apiKey": self._api_key},
            ensure_ascii=False,
        )
        try:
            result = subprocess.run(
                ["node", str(self._script_path), api_path, raw_body, options],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"调用 ima_api.cjs 失败：{exc}") from exc

        if result.returncode != 0:
            err_msg = result.stderr.strip() or "未知错误"
            raise RuntimeError(f"IMA API 调用失败：{err_msg}")

        stdout = result.stdout.strip()
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"raw": stdout}

    # ------------------------------------------------------------------ #
    # 知识库操作
    # ------------------------------------------------------------------ #
    def search_knowledge(
        self,
        query: str,
        kb_id: str | None = None,
        cursor: str = "",
    ) -> list[dict[str, Any]]:
        """在指定知识库中搜索内容。

        Args:
            query: 搜索关键词。
            kb_id: 知识库 ID。为空则无法搜索（返回空列表）。
            cursor: 分页游标（首次传空字符串）。

        Returns:
            搜索结果列表（``info_list``）。dry_run 模式返回空列表。
        """
        if not self.has_credentials():
            return []
        if not kb_id:
            return []
        try:
            resp = self._call_api(
                "openapi/wiki/v1/search_knowledge",
                body={
                    "query": query,
                    "knowledge_base_id": kb_id,
                    "cursor": cursor,
                },
            )
            if resp.get("code") != 0:
                return []
            data = resp.get("data", {})
            info_list = data.get("info_list", [])
            return info_list if isinstance(info_list, list) else []
        except RuntimeError:
            return []

    def search_knowledge_base(self, query: str = "") -> list[dict[str, Any]]:
        """按关键词搜索知识库列表。

        Args:
            query: 搜索关键词。为空字符串则返回所有知识库。

        Returns:
            知识库列表（``info_list``）。dry_run 模式返回空列表。
        """
        if not self.has_credentials():
            return []
        try:
            resp = self._call_api(
                "openapi/wiki/v1/search_knowledge_base",
                body={"query": query, "cursor": "", "limit": 20},
            )
            if resp.get("code") != 0:
                return []
            data = resp.get("data", {})
            info_list = data.get("info_list", [])
            return info_list if isinstance(info_list, list) else []
        except RuntimeError:
            return []

    def list_knowledge_bases(self) -> list[dict[str, Any]]:
        """列出所有知识库（等价于 ``search_knowledge_base(query="")``）。"""
        return self.search_knowledge_base(query="")

    # ------------------------------------------------------------------ #
    # 健康检查
    # ------------------------------------------------------------------ #
    def health_check(self) -> bool:
        """检查 IMA 服务是否可用。

        调用 ``search_knowledge_base`` 验证凭证有效性。无凭证时返回 False。
        """
        if not self.has_credentials():
            return False
        try:
            resp = self._call_api(
                "openapi/wiki/v1/search_knowledge_base",
                body={"query": "", "cursor": "", "limit": 1},
            )
            return resp.get("code") == 0
        except RuntimeError:
            return False
