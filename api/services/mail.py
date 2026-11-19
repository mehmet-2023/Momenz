from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from ..config import Settings

log = logging.getLogger("momenz.mail")


def _send_webhook(settings: Settings, to: str, subject: str, body: str) -> bool:
    """HTTPS mail köprüsüne (Google Apps Script) istek gönderir.

    Render free web servisleri 25/465/587 portlarını kapattığı için SMTP
    üretimde çalışmaz. Apps Script köprüsü Gmail hesabından gönderir ve
    yalnızca HTTPS (443) kullanır.
    """
    url = settings.mail_webhook_url.strip()
    secret = settings.mail_webhook_secret.strip()
    if not url or not secret:
        log.error(
            "MOMENZ_MAIL_WEBHOOK_URL ve MOMENZ_MAIL_WEBHOOK_SECRET birlikte "
            "tanımlanmalı; mail gönderilemedi: %s",
            to,
        )
        return False
    if not url.startswith("https://"):
        log.error("Mail webhook URL'i https:// ile başlamalı: %s", url)
        return False

    payload = json.dumps(
        {"secret": secret, "to": to, "subject": subject, "body": body}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Momenz/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=settings.mail_webhook_timeout
        ) as response:
            raw = response.read(4096).decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        log.warning("Mail webhook isteği başarısız: %s", exc)
        return False

    try:
        result = json.loads(raw) if raw else {}
    except ValueError:
        result = {}
    if isinstance(result, dict) and result.get("ok") is False:
        log.warning(
            "Mail webhook reddetti: %s", result.get("error", raw[:200] or "bilinmeyen")
        )
        return False
    return True


def send_mail(settings: Settings, to: str, subject: str, body: str) -> bool:
    """Mail gönderir.

    Öncelik: HTTPS webhook (Apps Script Gmail köprüsü). Webhook tanımlı
    değilse yerel geliştirme için Gmail SMTP (STARTTLS, 587) denenir.
    Prod'da SMTP ayarları yoksa fail-closed: sıfırlama bağlantısı gönderilmez.
    Geliştirmede hiçbir ayar yoksa konsola yazar.

    Kayıt doğrulama maili gönderilmez; yalnızca 'şifremi unuttum' akışı
    kullanılır.
    """
    if settings.mail_webhook_url or settings.mail_webhook_secret:
        return _send_webhook(settings, to, subject, body)

    if not settings.smtp_user or not settings.smtp_password:
        if settings.is_production:
            log.error(
                "Mail webhook'u veya MOMENZ_SMTP_USER / MOMENZ_SMTP_PASSWORD "
                "tanımlı değil; mail gönderilemedi: %s",
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
