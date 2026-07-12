"""服务连接器（开放 API 集成）。

提供 GitHub / Slack / 邮件 / IMA 知识库 / 通用 HTTP 等外部服务连接器，
供 WorkFlow 的 Step 调用。

所有服务均继承 :class:`~loopflow.services.base.Service`，支持：

- 无凭证时 dry_run（返回空列表/空结果，不抛异常）。
- ``health_check`` 验证连通性。
- 通过 :class:`~loopflow.services.base.ServiceRegistry` 单例统一注册与持久化。
"""

from loopflow.services.base import Service, ServiceConfig, ServiceRegistry
from loopflow.services.email import EmailService
from loopflow.services.github import GitHubService
from loopflow.services.http import HTTPService
from loopflow.services.ima import IMAService
from loopflow.services.slack import SlackService

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
