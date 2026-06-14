from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_email_smtp(*, to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email
    message.set_content(body)

    context = ssl.create_default_context()

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        client.send_message(message)


class EmailService:
    async def send_password_reset_email(self, *, to_email: str, reset_url: str) -> None:
        subject = "Сброс пароля — AI Platform"
        body = (
            "Вы запросили сброс пароля для аккаунта AI Platform.\n\n"
            f"Перейдите по ссылке, чтобы задать новый пароль:\n{reset_url}\n\n"
            "Ссылка действует ограниченное время. Если вы не запрашивали сброс, "
            "просто проигнорируйте это письмо."
        )

        if not settings.SMTP_HOST:
            logger.info("SMTP не настроен. Ссылка для сброса пароля (%s): %s", to_email, reset_url)
            return

        await asyncio.to_thread(
            _send_email_smtp,
            to_email=to_email,
            subject=subject,
            body=body,
        )
