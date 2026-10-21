"""Small SMTP adapter for account-authentication messages."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def validate_email_delivery_configuration() -> None:
    app_env = os.getenv("APP_ENV", "development").lower()
    backend = os.getenv("AUTH_EMAIL_BACKEND", "smtp" if app_env == "production" else "console").lower()
    if app_env == "production" and backend != "smtp":
        raise RuntimeError("Production requires AUTH_EMAIL_BACKEND=smtp")
    if backend != "smtp":
        return
    required = ("SMTP_HOST", "SMTP_FROM")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("SMTP configuration is incomplete: " + ", ".join(missing))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    if bool(username) != bool(password):
        raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
    if os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}:
        return
    if os.getenv("SMTP_STARTTLS", "true").lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("SMTP must use implicit TLS or STARTTLS")


def send_auth_email(to_email: str, subject: str, body: str) -> None:
    """Deliver auth mail. Console mode is only for local development."""
    app_env = os.getenv("APP_ENV", "development").lower()
    backend = os.getenv("AUTH_EMAIL_BACKEND", "smtp" if app_env == "production" else "console").lower()
    if backend == "console":
        if app_env == "production":
            raise RuntimeError("Console auth email delivery is forbidden in production")
        logger.warning("DEV-ONLY AUTH EMAIL recipient=%s subject=%s\n%s", to_email, subject, body)
        return
    if backend != "smtp":
        raise RuntimeError("Unsupported auth email backend")
    validate_email_delivery_configuration()

    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "465" if os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"} else "587"))
    timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
    if not 1 <= timeout <= 60:
        raise RuntimeError("SMTP_TIMEOUT_SECONDS must be between 1 and 60")
    if os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as server:
            _login_and_send(server, message)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            if os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes", "on"}:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            _login_and_send(server, message)


def _login_and_send(server, message: EmailMessage) -> None:
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    if username:
        server.login(username, password)
    server.send_message(message)
