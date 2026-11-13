"""Sending the few e-mails Haki sends (today: the password reset link).

Two backends, chosen by settings.mail_backend:
- "log" writes the link to the server log, for development. Prod refuses
  it at startup (app/config.py): whoever reads the logs would get the link.
- "smtp" sends through settings.smtp_host. Locally that is Mailpit from
  compose, which keeps every message and sends none on. A real provider is
  Andrei's choice (it costs money); any that speaks SMTP fits.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

# Only a server on this machine may be spoken to without TLS (Mailpit)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "mailpit"}


def reset_message(to: str, link: str) -> EmailMessage:
    """The reset e-mail. EmailMessage refuses CR or LF in a header, so an
    address can never add headers of its own."""
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = "Reset your Haki password"
    message.set_content(
        "Someone asked to reset the password of your Haki account.\n\n"
        f"To choose a new one, open this link within 30 minutes:\n{link}\n\n"
        "If it was not you, ignore this e-mail: your password stays as it is."
    )
    return message


def send(message: EmailMessage) -> None:
    """Send through SMTP, with TLS unless the server is local."""
    host, port = settings.smtp_host, settings.smtp_port
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if host not in LOCAL_HOSTS:
            smtp.starttls(context=ssl.create_default_context())
        smtp.send_message(message)


def send_password_reset(to: str, link: str) -> None:
    """Send the reset link to `to`, which must be the address stored for the
    account, never one taken from a request."""
    if settings.mail_backend == "log":
        # Development only (prod refuses this backend): the link, not the
        # address, so a log holds no personal data beyond what it must
        logger.warning("Password reset link (log backend): %s", link)
        return
    send(reset_message(to, link))
