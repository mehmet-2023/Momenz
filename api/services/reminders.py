from __future__ import annotations

import logging

from ..config import Settings
from ..db import D1Client
from ..errors import Conflict, NotFound
from ..repositories import events as event_repo
from ..repositories import reminders as repo
from ..schemas import MessageOut
from ..security import new_id
from .mail import send_mail

log = logging.getLogger("momenz.reminders")

_MAX_PER_EVENT = 5000


def subscribe(db: D1Client, slug: str, email: str) -> MessageOut:
    """Fotoğrafları hazır olmayan etkinlik için e-posta kaydı."""
    event = event_repo.get_by_slug(db, slug)
    if not event or not event.get("is_public", True):
        raise NotFound("Etkinlik bulunamadı.")
    if not event.get("drive_pending") and int(event.get("image_count") or 0) > 0:
        raise Conflict("Bu etkinliğin fotoğrafları zaten hazır.")

    if repo.total_count(db, str(event["id"])) >= _MAX_PER_EVENT:
        raise Conflict("Bu etkinlik için hatırlatma listesi dolu.")

    repo.add(db, new_id(), str(event["id"]), email)
    # Aynı e-posta tekrar gönderilse de aynı yanıt verilir: liste üyeliği
    # dışarıdan sorgulanamaz.
    return MessageOut(
        message="Fotoğraflar yüklendiğinde bu e-posta adresine haber vereceğiz."
    )


def notify_ready(db: D1Client, settings: Settings, folder_key: str) -> int:
    """Index tamamlandığında bekleyen hatırlatmalara tek seferlik mail atar."""
    rows = repo.pending_for_folder(db, folder_key)
    sent = 0
    for row in rows:
        slug = str(row.get("slug") or "")
        title = str(row.get("title") or "Etkinlik")
        if not slug:
            continue
        # Önce kaydı sahiplen: başka bir worker aynı kişiye ikinci mail atmaz.
        if not repo.claim(db, str(row["id"])):
            continue
        link = f"{settings.web_base_url.rstrip('/')}/events/{slug}"
        body = (
            f"{title} etkinliğinin fotoğrafları yüklendi.\n\n"
            f"Kendi fotoğraflarını bulmak için:\n{link}\n\n"
            "Bu e-postayı Momenz'de bu etkinlik için hatırlatma listesine "
            "kaydolduğun için alıyorsun."
        )
        if send_mail(
            settings,
            str(row["email"]),
            f"Momenz — {title} fotoğrafları hazır",
            body,
        ):
            sent += 1
        else:
            repo.release(db, str(row["id"]))
            log.warning(
                "Hatırlatma maili gönderilemedi; sonraki taramada tekrar denenecek: %s",
                row.get("email"),
            )
    if sent:
        log.info("%s etkinliği için %d hatırlatma maili gönderildi.", folder_key, sent)
    return sent
