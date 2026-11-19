from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .db import TursoClient, TursoError
from .db import schema as db_schema
from .errors import AppError, app_error_handler, unhandled_error_handler
from .middleware import (
    CSRFMiddleware,
    HealthExemptTrustedHostMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from .repositories import jobs as job_repo
from .repositories import users as user_repo
from .routes import auth, events, folders, images, jobs, search
from .schemas import HealthOut
from .services.search import SearchService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("momenz")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    if not settings.db_ready():
        raise RuntimeError(
            "Turso yapılandırması eksik. MOMENZ_TURSO_DATABASE_URL / "
            "MOMENZ_TURSO_AUTH_TOKEN değişkenlerini ayarla."
        )

    db = TursoClient(**settings.db_config)
    try:
        db.ping()
    except TursoError as exc:
        raise RuntimeError(f"Turso bağlantısı kurulamadı: {exc}") from exc
    try:
        db_schema.ensure_schema(db)
    except TursoError as exc:
        raise RuntimeError(f"Turso şeması hazırlanamadı: {exc}") from exc
    app.state.db = db
    app.state.user_cache = {}
    app.state.search = SearchService(settings)
    # /health DB'ye hiç dokunmasın: bağlantı ve şema yalnızca açılışta bir kez
    # doğrulanır, sonuç süreç boyunca ayakta tutulan bayraklardır.
    app.state.db_ok = True
    app.state.schema_ready = True

    try:
        recovered = job_repo.recover_stale(db, settings.job_stale_minutes)
        if recovered:
            log.warning("Yarım kalmış %d iş kuyruğa alındı.", recovered)
        user_repo.purge_expired(db)
    except TursoError as exc:
        log.error(
            "Turso bakım sorguları atlandı: %s | Şema eksikse `python scripts/migrate.py` çalıştır.",
            exc,
        )

    yield

    db.close()
    log.info("API kapatıldı.")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )
    app.state.settings = settings

    app.add_middleware(
        HealthExemptTrustedHostMiddleware, allowed_hosts=settings.trusted_hosts
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            settings.csrf_header,
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID", "X-Job-ID", "Location"],
    )
    app.add_middleware(CSRFMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestIdMiddleware)

    app.add_exception_handler(AppError, app_error_handler)  
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "İstek verisi geçersiz.",
                    "detail": [
                        {
                            "field": ".".join(str(part) for part in err.get("loc", [])[1:]),
                            "message": err.get("msg"),
                        }
                        for err in exc.errors()
                    ],
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "momenz-api"}

    @app.get("/health", response_model=HealthOut, tags=["system"])
    def health(request: Request) -> HealthOut:
        # Saf liveness: DB'ye istek atmaz. Turso bağlantısı/şeması lifespan'ta
        # bir kez doğrulanır; Render polling'i artık hiçbir satır okutmaz.
        ok = bool(getattr(request.app.state, "db_ok", False))
        return HealthOut(
            status="ok" if ok else "degraded",
            d1=ok,
            environment=settings.environment,
            time=datetime.now(timezone.utc),
            schema_ready=bool(getattr(request.app.state, "schema_ready", False)),
        )

    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(folders.router, prefix=prefix)
    app.include_router(events.router, prefix=prefix)
    app.include_router(events.public_router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(images.router, prefix=prefix)
    return app


app = create_app()
