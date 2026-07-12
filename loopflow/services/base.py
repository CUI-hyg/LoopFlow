"""服务连接器基类与注册表。

定义所有外部服务连接器（GitHub / Slack / 邮件 / IMA / HTTP）的公共抽象：

- :class:`ServiceConfig` — 服务的配置模型（名称、类型、凭证、基址、启用状态）。
- :class:`Service` — 服务连接器抽象基类，提供 ``health_check`` / ``test_connection``
  接口，并在 ``__repr__`` 中隐藏凭证，避免敏感信息落入日志。
- :class:`ServiceRegistry` — 单例注册表，管理已注册服务，支持持久化到
  ``~/.loopflow/services.json``（凭证字段经 Base64 编码，不落明文）。
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

__all__ = ["ServiceConfig", "Service", "ServiceRegistry", "SERVICES_FILE"]

# 服务配置持久化路径
SERVICES_FILE = Path.home() / ".loopflow" / "services.json"

# 凭证编码前缀，标识该字段已编码（非明文）
_CRED_ENCODED_PREFIX = "enc:b64:"


class ServiceConfig(BaseModel):
    """服务配置。

    Attributes:
        name: 服务实例名称（唯一标识）。
        service_type: 服务类型（github / slack / email / ima / http）。
        credentials: 凭证字典（token、密码等敏感信息）。
        base_url: 服务 API 基址。
        enabled: 是否启用。
    """

    name: str
    service_type: str
    credentials: dict[str, Any] = Field(default_factory=dict)
    base_url: str = ""
    enabled: bool = True

    # pydantic v2 允许任意类型，但需显式配置
    model_config = {"extra": "allow"}


class Service(ABC):
    """服务连接器抽象基类。

    子类需实现 :meth:`health_check`。基类提供凭证安全存储（``__repr__`` 隐藏
    敏感字段）与 ``test_connection`` 通用实现。
    """

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------ #
    # 凭证访问
    # ------------------------------------------------------------------ #
    @property
    def credentials(self) -> dict[str, Any]:
        """获取凭证字典。"""
        return self.config.credentials

    @property
    def name(self) -> str:
        """服务名称。"""
        return self.config.name

    @property
    def enabled(self) -> bool:
        """是否启用。"""
        return self.config.enabled

    def has_credentials(self) -> bool:
        """是否有凭证（无凭证则进入 dry_run 模式）。"""
        return bool(self.config.credentials)

    # ------------------------------------------------------------------ #
    # 抽象接口
    # ------------------------------------------------------------------ #
    @abstractmethod
    def health_check(self) -> bool:
        """检查服务是否可用。无凭证时返回 False。"""

    # ------------------------------------------------------------------ #
    # 通用实现
    # ------------------------------------------------------------------ #
    def test_connection(self) -> dict[str, Any]:
        """测试连接并返回详情。

        返回 dict 包含服务名称、类型、是否健康、是否有凭证等信息。
        """
        result: dict[str, Any] = {
            "service": self.config.name,
            "type": self.config.service_type,
            "has_credentials": self.has_credentials(),
            "healthy": False,
            "error": "",
        }
        if not self.has_credentials():
            result["error"] = "无凭证（dry_run 模式）"
            return result
        try:
            result["healthy"] = self.health_check()
        except Exception as exc:  # noqa: BLE001 — 健康检查不应抛异常
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    # ------------------------------------------------------------------ #
    # 凭证安全：__repr__ 隐藏敏感字段
    # ------------------------------------------------------------------ #
    def __repr__(self) -> str:
        cred_count = len(self.config.credentials)
        return (
            f"<{type(self).__name__} name={self.config.name!r} "
            f"type={self.config.service_type!r} "
            f"enabled={self.config.enabled} "
            f"credentials={cred_count}个(已隐藏)>"
        )

    def __str__(self) -> str:
        return self.__repr__()


class ServiceRegistry:
    """服务注册表（单例）。

    管理已注册的服务连接器，支持：

    - :meth:`register` — 注册服务实例。
    - :meth:`get` — 按名称获取服务实例。
    - :meth:`list_services` — 列出所有服务配置。
    - :meth:`load` / :meth:`save` — 从 ``~/.loopflow/services.json`` 加载/保存。

    凭证字段在持久化时经 Base64 编码，不落明文到文件。
    """

    _instance: ClassVar["ServiceRegistry | None"] = None

    def __new__(cls) -> "ServiceRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._services: dict[str, Service] = {}
            cls._instance._loaded = False
        return cls._instance

    # ------------------------------------------------------------------ #
    # 注册 / 获取 / 列表
    # ------------------------------------------------------------------ #
    def register(self, service: Service) -> None:
        """注册一个服务实例。同名服务会被覆盖。"""
        self._services[service.config.name] = service
        self.save()

    def get(self, name: str) -> Service | None:
        """按名称获取服务实例；不存在则返回 None。"""
        if not self._loaded:
            self.load()
        return self._services.get(name)

    def list_services(self) -> list[ServiceConfig]:
        """列出所有已注册服务的配置。"""
        if not self._loaded:
            self.load()
        return [s.config for s in self._services.values()]

    def remove(self, name: str) -> bool:
        """移除已注册服务；返回是否成功移除。"""
        if name in self._services:
            del self._services[name]
            self.save()
            return True
        return False

    def clear(self) -> None:
        """清空所有已注册服务。"""
        self._services.clear()
        self.save()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    def save(self) -> None:
        """将所有服务配置保存到 ``~/.loopflow/services.json``。

        凭证字段经 Base64 编码后存储，不落明文。文件权限设为 0o600（仅
        所有者可读写），防止其他用户读取凭证。
        """
        SERVICES_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: list[dict[str, Any]] = []
        for svc in self._services.values():
            cfg = svc.config.model_dump()
            # 凭证编码
            cfg["credentials"] = _encode_credentials(svc.config.credentials)
            data.append(cfg)
        payload = {"services": data}
        SERVICES_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # 设置文件权限为仅所有者可读写，防止其他用户读取凭证
        try:
            os.chmod(SERVICES_FILE, 0o600)
        except OSError:
            pass

    def load(self) -> None:
        """从 ``~/.loopflow/services.json`` 加载服务配置。

        文件不存在或解析失败时静默返回（保持空注册表）。对非 dict 结构、
        非法凭证编码等异常均安全跳过，不抛异常。
        """
        self._loaded = True
        if not SERVICES_FILE.exists():
            return
        try:
            payload = json.loads(SERVICES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(payload, dict):
            return
        services = payload.get("services", [])
        if not isinstance(services, list):
            return
        for item in services:
            if not isinstance(item, dict):
                continue
            try:
                cred_raw = item.get("credentials", {})
                if isinstance(cred_raw, str):
                    creds = _decode_credentials(cred_raw)
                elif isinstance(cred_raw, dict):
                    creds = cred_raw
                else:
                    creds = {}
                item["credentials"] = creds
                config = ServiceConfig(**item)
                service = _build_service(config)
                if service is not None:
                    self._services[config.name] = service
            except (binascii.Error, TypeError, ValueError):
                # 凭证解码失败或配置非法时跳过该条目，不影响其他服务
                continue


# ---------------------------------------------------------------------- #
# 凭证编码 / 解码（Base64 混淆，防止明文落盘）
# ---------------------------------------------------------------------- #
def _encode_credentials(creds: dict[str, Any]) -> str:
    """将凭证字典编码为 Base64 字符串。

    注意：Base64 仅是编码（可逆），并非加密。本方法用于避免明文落盘，
    不能抵御有文件读权限的攻击者。生产环境建议使用 ``keyring`` 等系统
    凭证管理工具存储敏感凭证。
    """
    raw = json.dumps(creds, ensure_ascii=False).encode("utf-8")
    return _CRED_ENCODED_PREFIX + base64.b64encode(raw).decode("ascii")


def _decode_credentials(encoded: str) -> dict[str, Any]:
    """将 Base64 编码的凭证字符串解码为字典。"""
    if not isinstance(encoded, str) or not encoded.startswith(_CRED_ENCODED_PREFIX):
        return {}
    raw = base64.b64decode(encoded[len(_CRED_ENCODED_PREFIX):])
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------- #
# 服务工厂：根据 service_type 构建对应 Service 实例
# ---------------------------------------------------------------------- #
def _build_service(config: ServiceConfig) -> Service | None:
    """根据 ServiceConfig 的 service_type 构建对应 Service 实例。

    延迟导入避免循环依赖。
    """
    stype = config.service_type.lower()
    creds = config.credentials

    if stype == "github":
        from loopflow.services.github import GitHubService

        return GitHubService(
            token=creds.get("token", ""),
            repo=creds.get("repo", ""),
            name=config.name,
        )
    if stype == "slack":
        from loopflow.services.slack import SlackService

        return SlackService(
            token=creds.get("token", ""),
            channel=creds.get("channel", ""),
            name=config.name,
        )
    if stype == "email":
        from loopflow.services.email import EmailService

        return EmailService(
            imap_host=creds.get("imap_host", ""),
            smtp_host=creds.get("smtp_host", ""),
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            name=config.name,
        )
    if stype == "ima":
        from loopflow.services.ima import IMAService

        return IMAService(name=config.name)
    if stype == "http":
        from loopflow.services.http import HTTPService

        return HTTPService(
            base_url=config.base_url,
            headers=creds.get("headers"),
            auth_token=creds.get("auth_token", ""),
            name=config.name,
        )
    return None
