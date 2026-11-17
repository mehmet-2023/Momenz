from __future__ import annotations

import logging

import requests

from ..config import Settings

log = logging.getLogger("momenz.mail")


def send_mail(settings: Settings, to: str, subject: str, body: str) -> bool:
    """Resend varsa gönderir, yoksa geliştirmede konsola yazar.

    Tek kullanım amacı 'şifremi unuttum': kayıt/doğrulama maili gönderilmez.
    Prod'da API anahtarı yoksa sıfırlama bağlantısı gönderilemez (fail-closed).
    """
    if settings.resend_api_key:
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": settings.mail_from,
                    "to": [to],
                    "subject": subject,
                    "text": body,
                },
                timeout=(5, 20),
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            log.warning("Mail gönderilemedi: %s", exc)
            return False

    if settings.is_production:
        log.error("MOMENZ_RESEND_API_KEY tanımlı değil; mail gönderilemedi: %s", to)
        return False

    log.warning("[DEV MAIL] %s | %s\n%s", to, subject, body)
    return True
