"""邮件服务连接器。

使用标准库 ``imaplib``（收）+ ``smtplib``（发）+ ``email``（消息构造与解析）
实现，不引入额外依赖。

无凭证时自动进入 ``dry_run`` 模式（返回空列表，不抛异常）。
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from typing import Any

from loopkits.services.base import Service, ServiceConfig

__all__ = ["EmailService"]


class EmailService(Service):
    """邮件服务连接器（IMAP 收 + SMTP 发）。

    Args:
        imap_host: IMAP 服务器地址（如 ``imap.gmail.com``）。
        smtp_host: SMTP 服务器地址（如 ``smtp.gmail.com``）。
        username: 邮箱账号。
        password: 邮箱密码或应用专用密码。
        name: 服务实例名称（用于注册表）。
    """

    def __init__(
        self,
        imap_host: str = "",
        smtp_host: str = "",
        username: str = "",
        password: str = "",
        name: str = "email",
    ) -> None:
        creds: dict[str, Any] = {}
        if imap_host:
            creds["imap_host"] = imap_host
        if smtp_host:
            creds["smtp_host"] = smtp_host
        if username:
            creds["username"] = username
        if password:
            creds["password"] = password
        config = ServiceConfig(
            name=name,
            service_type="email",
            credentials=creds,
            base_url="",
            enabled=True,
        )
        super().__init__(config)
        self._imap_host = imap_host
        self._smtp_host = smtp_host
        self._username = username
        self._password = password

    # ------------------------------------------------------------------ #
    # IMAP 收件
    # ------------------------------------------------------------------ #
    def list_unread(self, limit: int = 20) -> list[dict[str, Any]]:
        """读取未读邮件。

        Args:
            limit: 最多返回的邮件数。

        Returns:
            邮件列表，每条包含 ``subject``、``from``、``date``、``body`` 字段。
            dry_run 模式返回空列表。
        """
        if not self._has_credentials():
            return []
        conn = None
        try:
            conn = imaplib.IMAP4_SSL(self._imap_host)
            conn.login(self._username, self._password)
            conn.select("INBOX")
            # 搜索未读邮件
            status, data = conn.search(None, "UNSEEN")
            if status != "OK":
                return []
            ids = data[0].split() if data and data[0] else []
            # 取最近 limit 封（倒序）
            ids = ids[-limit:] if len(ids) > limit else ids
            results: list[dict[str, Any]] = []
            for mail_id in reversed(ids):
                status, fetch_data = conn.fetch(mail_id, "(RFC822)")
                if status != "OK" or not fetch_data or not fetch_data[0]:
                    continue
                raw = fetch_data[0][1] if isinstance(fetch_data[0], tuple) else b""
                msg = email.message_from_bytes(raw)
                results.append(_parse_message(msg))
            return results
        except (OSError, imaplib.IMAP4.error):
            return []
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:  # noqa: BLE001 — 清理时忽略错误
                    pass

    # ------------------------------------------------------------------ #
    # SMTP 发件
    # ------------------------------------------------------------------ #
    def send(self, to: str, subject: str, body: str) -> bool:
        """发送邮件。

        Args:
            to: 收件人地址。
            subject: 邮件主题。
            body: 邮件正文（纯文本）。

        Returns:
            是否发送成功。dry_run 模式返回 False。
        """
        if not self._has_credentials():
            return False
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._username
        msg["To"] = to
        msg["Date"] = email.utils.formatdate(localtime=True)
        try:
            with smtplib.SMTP_SSL(self._smtp_host, 465, timeout=30) as server:
                server.login(self._username, self._password)
                server.sendmail(self._username, [to], msg.as_string())
            return True
        except (OSError, smtplib.SMTPException):
            return False

    # ------------------------------------------------------------------ #
    # 健康检查
    # ------------------------------------------------------------------ #
    def health_check(self) -> bool:
        """检查邮件服务是否可用（尝试 IMAP 登录）。

        无凭证时返回 False。
        """
        if not self._has_credentials():
            return False
        conn = None
        try:
            conn = imaplib.IMAP4_SSL(self._imap_host)
            conn.login(self._username, self._password)
            return True
        except (OSError, imaplib.IMAP4.error):
            return False
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:  # noqa: BLE001
                    pass

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _has_credentials(self) -> bool:
        """检查是否具备完整的邮件凭证。"""
        return bool(
            self._imap_host
            and self._smtp_host
            and self._username
            and self._password
        )

    def has_credentials(self) -> bool:  # noqa: D401 — 覆盖基类
        """是否有完整凭证（IMAP/SMTP/账号/密码均需存在）。"""
        return self._has_credentials()


# ---------------------------------------------------------------------- #
# 邮件解析辅助
# ---------------------------------------------------------------------- #
def _decode_str(value: str) -> str:
    """解码邮件头部字段（可能含编码段）。"""
    if not value:
        return ""
    parts = decode_header(value)
    decoded: list[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def _parse_message(msg: email.message.Message) -> dict[str, Any]:
    """将 ``email.message.Message`` 解析为简洁字典。"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition", ""))
            if ctype == "text/plain" and "attachment" not in cdisp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return {
        "subject": _decode_str(msg.get("Subject", "")),
        "from": _decode_str(msg.get("From", "")),
        "date": msg.get("Date", ""),
        "body": body,
    }
