#!/usr/bin/env python3
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "chatplatform.noreply@gmail.com"
SMTP_PASSWORD = "wuvjkbloezwceuxp"

TO_EMAIL = "dimonchechulov@gmail.com"


def send_test_email():
    message = EmailMessage()
    message["Subject"] = "SMTP test — AI Platform"
    message["From"] = SMTP_USER
    message["To"] = TO_EMAIL
    message.set_content("Тестовое письмо")

    context = ssl.create_default_context()

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()

        client.login(SMTP_USER, SMTP_PASSWORD)
        client.send_message(message)

    print("Письмо отправлено")


if __name__ == "__main__":
    send_test_email()
