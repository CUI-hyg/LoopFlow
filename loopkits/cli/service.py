"""``loopflow service`` 子命令组。

提供服务连接器的命令行管理：

- ``loopflow service add <name> --type <type> --token <token>``：添加服务。
- ``loopflow service list``：列出已注册服务。
- ``loopflow service health [name]``：健康检查。
"""

from __future__ import annotations

import click

from loopkits.services import (
    EmailService,
    GitHubService,
    HTTPService,
    IMAService,
    ServiceRegistry,
    SlackService,
)

# 支持的服务类型映射
_SERVICE_TYPES = {
    "github": GitHubService,
    "slack": SlackService,
    "email": EmailService,
    "ima": IMAService,
    "http": HTTPService,
}


@click.group()
def service() -> None:
    """管理服务连接器（GitHub / Slack / 邮件 / IMA / HTTP）。"""


@service.command("add")
@click.argument("name")
@click.option(
    "--type",
    "service_type",
    required=True,
    type=click.Choice(list(_SERVICE_TYPES.keys())),
    help="服务类型",
)
@click.option("--token", default="", help="认证 Token（GitHub / Slack 等）")
@click.option("--repo", default="", help="GitHub 仓库全名（owner/repo）")
@click.option("--channel", default="", help="Slack 频道")
@click.option("--imap-host", default="", help="IMAP 服务器地址")
@click.option("--smtp-host", default="", help="SMTP 服务器地址")
@click.option("--username", default="", help="邮箱账号")
@click.option("--password", default="", help="邮箱密码")
@click.option("--base-url", default="", help="服务 API 基址（HTTP 通用）")
@click.option("--auth-token", default="", help="Bearer Token（HTTP 通用）")
def service_add(
    name: str,
    service_type: str,
    token: str,
    repo: str,
    channel: str,
    imap_host: str,
    smtp_host: str,
    username: str,
    password: str,
    base_url: str,
    auth_token: str,
) -> None:
    """添加一个服务连接器。"""
    if service_type == "github":
        svc = GitHubService(token=token, repo=repo, name=name)
    elif service_type == "slack":
        svc = SlackService(token=token, channel=channel, name=name)
    elif service_type == "email":
        svc = EmailService(
            imap_host=imap_host,
            smtp_host=smtp_host,
            username=username,
            password=password,
            name=name,
        )
    elif service_type == "ima":
        svc = IMAService(name=name)
    elif service_type == "http":
        svc = HTTPService(base_url=base_url, auth_token=auth_token, name=name)
    else:
        click.echo(f"不支持的服务类型：{service_type}", err=True)
        raise SystemExit(1)

    registry = ServiceRegistry()
    registry.register(svc)
    click.echo(f"✓ 已注册服务：{name}（类型：{service_type}）")
    if not svc.has_credentials() and service_type != "http":
        click.echo("  ⚠ 未提供凭证，将以 dry_run 模式运行")


@service.command("list")
def service_list() -> None:
    """列出已注册的服务。"""
    registry = ServiceRegistry()
    configs = registry.list_services()
    if not configs:
        click.echo("（暂无已注册服务）")
        return
    click.echo(f"已注册服务（共 {len(configs)} 个）：")
    for cfg in configs:
        svc = registry.get(cfg.name)
        has_cred = svc.has_credentials() if svc is not None else bool(cfg.credentials)
        cred_status = "有凭证" if has_cred else "无凭证(dry_run)"
        enabled = "启用" if cfg.enabled else "禁用"
        click.echo(
            f"  • {cfg.name} — 类型: {cfg.service_type} | "
            f"状态: {enabled} | 凭证: {cred_status}"
        )


@service.command("health")
@click.argument("name", required=False)
def service_health(name: str | None) -> None:
    """对服务进行健康检查。

    NAME 为空时检查所有已注册服务。
    """
    registry = ServiceRegistry()
    if name:
        svc = registry.get(name)
        if svc is None:
            click.echo(f"未找到服务：{name}", err=True)
            raise SystemExit(1)
        _check_one(svc)
    else:
        configs = registry.list_services()
        if not configs:
            click.echo("（暂无已注册服务）")
            return
        for cfg in configs:
            svc = registry.get(cfg.name)
            if svc is not None:
                _check_one(svc)


def _check_one(svc: object) -> None:
    """对单个服务执行健康检查并输出结果。"""
    result = svc.test_connection()  # type: ignore[attr-defined]
    name = result.get("service", "?")
    stype = result.get("type", "?")
    healthy = result.get("healthy", False)
    has_cred = result.get("has_credentials", False)
    error = result.get("error", "")

    status = "✓ 健康" if healthy else "✗ 不可用"
    cred = "有凭证" if has_cred else "无凭证"
    line = f"  • {name}（{stype}）— {status} | {cred}"
    if error:
        line += f" | {error}"
    click.echo(line)
