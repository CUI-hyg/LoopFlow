"""服务连接器（开放 API 集成）。

提供 GitHub / Slack / 邮件 / IMA 知识库 / 通用 HTTP 等外部服务连接器，
供 WorkFlow 的 Step 调用。

所有服务均继承 :class:`~loopkits.services.base.Service`，支持：

- 无凭证时 dry_run（返回空列表/空结果，不抛异常）。
- ``health_check`` 验证连通性。
- 通过 :class:`~loopkits.services.base.ServiceRegistry` 单例统一注册与持久化。
"""

from loopkits.services.base import Service, ServiceConfig, ServiceRegistry
from loopkits.services.email import EmailService
from loopkits.services.github import GitHubService
from loopkits.services.http import HTTPService
from loopkits.services.ima import IMAService
from loopkits.services.slack import SlackService

__all__ = [
    # 基类
    "Service",
    "ServiceConfig",
    "ServiceRegistry",
    # 服务连接器
    "GitHubService",
    "SlackService",
    "EmailService",
    "IMAService",
    "HTTPService",
]
