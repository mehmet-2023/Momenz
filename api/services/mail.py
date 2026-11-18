from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from ..config import Settings

log = logging.getLogger("momenz.mail")


def send_mail(settings: Settings, to: str, subject: str, body: str) -> bool:
    """Gmail SMTP ile mail gönderir (STARTTLS, 587).

    Resend kaldırıldı. Gmail App Password kullanılır; kota günlük ~500
    (bireysel) / ~2000 (Workspace) olduğu için kayıt doğrulama maili
    gönderilmez, yalnızca 'şifremi unuttum' akışı kullanılır.

    Prod'da SMTP ayarları yoksa fail-closed: sıfırlama bağlantısı gönderilmez.
    Geliştirmede ayar yoksa konsola yazar.
    """
    if not settings.smtp_user or not settings.smtp_password:
        if settings.is_production:
            log.error(
                "MOMENZ_SMTP_USER / MOMENZ_SMTP_PASSWORD tanımlı değil; mail gönderilemedi: %s",
                to,
            )
            return False
        log.warning("[DEV MAIL] %s | %s\n%s", to, subject, body)
        return True

    sender = settings.smtp_user
    # Gmail, From adresinin hesapla (veya doğrulanmış alias) aynı olmasını ister.
    # no-reply@momenz.com alan adı Gmail'de doğrulanmadıysa gönderim reddedilir.
    if "@" not in settings.mail_from:
        sender = settings.smtp_user
    elif settings.mail_from.endswith("@gmail.com") or settings.mail_from.endswith(
        settings.smtp_user.split("@")[-1]
    ):
        sender = settings.mail_from
    else:
        log.warning(
            "mail_from (%s) SMTP kullanıcı alan adıyla eşleşmiyor; From=%s kullanılıyor.",
            settings.mail_from,
            settings.smtp_user,
        )

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
        ) as client:
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
            client.login(settings.smtp_user, settings.smtp_password)
            client.send_message(message)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("Gmail SMTP ile mail gönderilemedi: %s", exc)
        return False
