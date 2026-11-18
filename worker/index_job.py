from __future__ import annotations

import argparse
import logging
import os
import time
import uuid
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
log = logging.getLogger("momenz.worker")

# NOT: api/core importları fonksiyonların içinde yapılır. Modal CLI dosyayı
# lokal olarak import edip `app` nesnesini arar; bu venv'de proje paketleri
# kurulu olmadığı için importlar üst seviyede olmamalı. Modal görüntüsünün
# içinde requirements-api.txt kurulu olduğundan çalışma zamanında sorun yok.


def run_job(settings: Any, job: dict) -> dict[str, Any]:
    from api.db import D1Client
    from api.repositories import folders as folder_repo
    from api.repositories import jobs as job_repo
    from api.services.drive import get_drive_client
    from core.config import (
        DEFAULT_DET_THRESHOLD,
        DEFAULT_MAX_FACES,
        DEFAULT_MIN_FACE,
        DEFAULT_THUMB_SIZE,
    )
    from core.d1_store import D1Store
    from core.face_engine import FaceEnginePool, ensure_models
    from core.pg_index_store import PgIndexStore
    from core.pipeline import IndexOptions, build_index

    worker_id = f"{os.uname().nodename}:{uuid.uuid4().hex[:8]}"
    db = D1Client(**settings.d1_config)
    claimed = job_repo.claim_by_id(db, str(job["id"]), worker_id)
    if not claimed:
        log.info("Job %s başka bir worker tarafından alındı.", job["id"])
        return {"status": "skipped"}

    folder_key = str(claimed["folder_key"])
    payload = claimed.get("payload") or {}
    try:
        # Makinenin tüm çekirdeklerini kullan: her worker'ın kendi yüz motoru
        # olsun (tek FaceEngine RLock ile analizi serileştiriyordu).
        cpu = max(1, min(8, os.cpu_count() or 4))
        yunet, sface = ensure_models()
        engine = FaceEnginePool(yunet, sface, size=cpu, num_threads=1)
        store = PgIndexStore(D1Store(settings.d1_config), folder_key)
        client = get_drive_client(settings)

        last_write = {"done": -1}

        def on_progress(done: int, total: int, skipped: int, counters: dict) -> None:
            # D1'e her fotoğrafta yazma yapmayız; %5 veya 50 adım aralığı.
            if done == total or done - last_write["done"] >= 50:
                last_write["done"] = done
                job_repo.update_progress(
                    db,
                    str(claimed["id"]),
                    worker_id,
                    progress=(done / total) if total else 1.0,
                    processed=done,
                    total=total,
                )

        summary = build_index(
            client=client,
            engine=engine,
            store=store,
            folder_id=str(payload.get("folder_id") or ""),
            resource_key=payload.get("resource_key"),
            options=IndexOptions(
                include_subfolders=bool(payload.get("include_subfolders", True)),
                thumb_size=int(payload.get("thumb_size") or DEFAULT_THUMB_SIZE),
                det_threshold=DEFAULT_DET_THRESHOLD,
                min_face=DEFAULT_MIN_FACE,
                max_faces=DEFAULT_MAX_FACES,
                force=claimed.get("kind") == "reindex",
                workers=cpu,
                chunk_size=64,
                sync_batch=100,
            ),
            on_progress=on_progress,
        )
        store.flush()
        # Fotoğraf sayısı Drive metadatasından gelsin: klasörde bulunan tüm
        # görsellerin sayısı index sonunda drive_folders.meta'ya yazılır.
        total_found = int(summary.get("total_found") or 0)
        if total_found:
            store.set_meta("folder_count", str(total_found))
        version = folder_repo.bump_version(db, folder_key)

        counters = summary.get("counters") or {}
        result = {
            "processed": int(summary.get("processed") or 0),
            "skipped": int(summary.get("skipped") or 0),
            "photos": total_found,
            "faces": int(counters.get("faces") or 0),
            "version": version,
        }
        job_repo.finish(db, str(claimed["id"]), worker_id, result)
        log.info("Job %s bitti: %s", claimed["id"], result)
        return {"status": "done", **result}
    except Exception as exc:
        log.exception("Job %s başarısız", claimed["id"])
        job_repo.fail(db, str(claimed["id"]), worker_id, f"{type(exc).__name__}: {exc}")
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


def poll_once(settings: Any) -> bool:
    from api.db import D1Client
    from api.repositories import jobs as job_repo

    db = D1Client(**settings.d1_config)
    try:
        recovered = job_repo.recover_stale(db, settings.job_stale_minutes)
        if recovered:
            log.warning("%d yarım kalmış iş kuyruğa alındı.", recovered)
        # Claim'i run_job içinde yapıyoruz; burada sadece aday id okuyoruz.
        # Böylece iki worker aynı işi görse bile WHERE status='queued' koşulu
        # (claim_by_id RETURNING) yalnızca birinin kazanmasını sağlar.
        candidate = db.query_one(
            "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        )
        if not candidate:
            return False
        # run_job -> claim_by_id zaten tüm satırı RETURNING ile okur; ayrıca
        # job_repo.get çağrısı gereksiz bir D1 okumasıydı.
        run_job(settings, {"id": str(candidate["id"])})
        return True
    finally:
        db.close()


def main() -> None:
    from api.config import get_settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.d1_ready():
        raise SystemExit("D1 ayarları eksik.")
    if args.once:
        poll_once(settings)
        return
    log.info("Worker başladı. Job bekleniyor...")
    while True:
        try:
            worked = poll_once(settings)
        except Exception as exc:
            log.error("Poll hatası: %s", exc)
            worked = False
        if not worked:
            time.sleep(max(1.0, settings.job_poll_seconds))


# ------------------------------------------------------------------ Modal
try:  # Modal kuruluysa serverless entrypoint'leri de tanımla.
    import modal

    modal_image = (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("libgl1", "libglib2.0-0")
        .pip_install_from_requirements("requirements-api.txt")
        # add_local_* her zaman EN SON gelmeli: Modal bunları build sonrası
        # mount eder; sonrasında bir build step gelirse deploy hata veriyor.
        # api/ ve core/ /app altında; Python path'e eklemezsek import patlar.
        .workdir("/app")
        .env({"PYTHONPATH": "/app"})
        .add_local_dir("core", "/app/core")
        .add_local_dir("api", "/app/api")
    )
    modal_app = modal.App(
        "momenz-indexer", image=modal_image, secrets=[modal.Secret.from_name("momenz")]
    )
    # Modal CLI `modal deploy worker/index_job.py` için standart isim.
    app = modal_app

    @modal_app.function(timeout=3600, cpu=8, memory=4096)
    def modal_index_job(job_id: str) -> dict[str, Any]:
        from api.config import get_settings

        settings = get_settings()
        # claim_by_id tek UPDATE ... RETURNING ile hem atomik claim yapar hem
        # tüm job alanlarını döner. Ayrı SELECT (1 D1 okuma) gereksizdi.
        return run_job(settings, {"id": job_id})

    @modal_app.function(schedule=modal.Period(minutes=1), timeout=120)
    def modal_dispatcher() -> dict[str, int]:
        from api.config import get_settings
        from api.db import D1Client

        log.info("Dispatcher çalışıyor (build=2026-11-18-d)")
        settings = get_settings()
        db = D1Client(**settings.d1_config)
        try:
            # Önce COUNT(*) + sonra SELECT = iki D1 isteğiydi. Satır sayısı
            # zaten elimizde; ikinci sorguyu kaldırdık.
            rows = db.query(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 20"
            )
        finally:
            db.close()
        for row in rows:
            modal_index_job.spawn(str(row["id"]))
        return {"queued": len(rows), "spawned": len(rows)}

except ImportError:
    modal_app = None  # type: ignore[assignment]


if __name__ == "__main__":
    main()
