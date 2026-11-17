# Momenz — FastAPI ürün iskeleti

Streamlit prototipi `app.py` olarak duruyor (referans/karşılaştırma için).
Yeni ürün katmanı **FastAPI + Cloudflare D1 + çok kullanıcılı auth** üzerine kurulu.

## Mimari

```
web/ (Next.js, Vercel)  ──Cookie/JWT──▶  api/ (FastAPI, Cloud Run / Oracle VM)
                                            │
                          ┌─────────────────┼──────────────────┐
                          ▼                 ▼                  ▼
                   repositories/      services/search    worker/index_job
                   (D1, owner_id)     (sıcak matris)     (Modal / VM)
                          │                 │                  │
                          └──────── Cloudflare D1 ─────────────┘
                                  (source of truth)
```

- **D1 korunur.** Mevcut `drive_face_index`, `drive_folders` tabloları kullanılır.
  Yalnızca `users`, `refresh_tokens`, `verification_tokens`, `jobs`,
  `folder_index_versions` eklenir ve `drive_folders.owner_id` kolonu gelir.
- **Arama:** `search_embeddings` (cosine) aynı, ama matris her istekte D1'den
  çekilmez. `folder_index_versions` ile versiyon kontrollü LRU cache.
- **Indexleme:** HTTP isteğinin içinde değil; D1 job kuyruğundan worker çeker.
  Worker bitince versiyonu artırır, cache kendiliğinden tazelenir.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-api.txt

python scripts/gen_env.py          # .env + rastgele JWT secret (600 yetkisi)
# .env içine D1 ve Google bilgilerini gir

python scripts/migrate.py
python scripts/bootstrap_admin.py admin@domain.com

uvicorn api.main:app --reload
```

API: `http://localhost:8000/docs` · Health: `/health`

Worker (yerel): `python -m worker.index_job`
Worker (Modal): `modal deploy worker/index_job.py`

## API uçları

| Method | Path | Açıklama |
|---|---|---|
| GET | `/auth/csrf` | CSRF cookie'sini yeniler (double-submit) |
| POST | `/auth/register` | Kayıt + doğrulama maili |
| POST | `/auth/verify?token=…` | E-posta doğrulama |
| POST | `/auth/login` | Access + refresh cookie, rotation |
| POST | `/auth/refresh` | Yeni token çifti (eski token iptal) |
| POST | `/auth/logout`, `/logout-all` | Oturum(ları) kapat |
| GET | `/auth/me` | Profil |
| POST | `/auth/password/forgot`, `/password/reset` | Şifre sıfırlama |
| GET/POST | `/folders` | Klasör listesi / ekle + job oluştur |
| GET/DELETE | `/folders/{key}` | Detay / sil |
| GET | `/jobs`, `/jobs/{id}` | İş durumu (frontend polling) |
| POST | `/jobs/{id}/cancel` | İptal |
| POST | `/search` | multipart: `folder_key`, `file`, `threshold` |
| GET | `/images/{id}/thumb`, `/download` | Yetki kontrollü proxy + disk cache |
| POST | `/images/preview.zip` | Önizleme ZIP (streaming) |

## Güvenlik notları

- JWT secret **rastgele üretilir** (`scripts/gen_env.py`); prod'da kısa/placeholder
  secret ile uygulama **açılmaz** (`api/config.py` model validator).
- Access token 15 dk, httpOnly + Secure + SameSite cookie. Refresh 30 gün,
  D1'de **SHA-256 fingerprint** olarak saklanır; rotation + reuse detection var.
- Cookie ile yazma isteklerinde **CSRF header zorunlu** (`X-CSRF-Token`).
  Bearer kullanan API istemcileri CSRF'e tabii değil.
- Tüm D1 sorguları parametreli; her kayıt `owner_id` ile izole edilir.
- Şifreler **argon2id** ile hash'lenir. Login rate-limit, user enumeration
  koruması, security headers, CSP, HSTS, TrustedHost açık.
- `credentials.json` / `.streamlit/secrets.toml` / `.env` git'e girmez.
- Frontend token'ları `localStorage`'a **yazmamalı**; cookie'leri kullanmalı.
  Response body'sindeki token'lar yalnızca sunucu/sunucu istemciler içindir.

Prod öncesi yapılacaklar: mail sağlayıcısı (`MOMENZ_RESEND_API_KEY`) tanımla,
`MOMENZ_ENVIRONMENT=prod`, `MOMENZ_COOKIE_SECURE=true`, gerçek domain'leri
`TRUSTED_HOSTS` / `CORS_ORIGINS` yaz.

## Hosting

Kod platform-agnostik. `Dockerfile` her yerde aynı çalışır. Aktif seçim:

```
web/ (Next.js)      → Vercel free
api/ (FastAPI)      → Render free  · Web Service · Docker · /health
keepalive           → Cloudflare Worker Cron (10 dk)
index worker        → Modal free kredi
veri                → Cloudflare D1
```

`render.yaml`, `deploy/wrangler.toml` ve `deploy/keepalive-worker.js` hazır.

Tasarım kuralları: `docs/DESIGN.md` (mevcut siyah/beyaz, mono tipografi korunur).

---

## Local'de ayağa kaldırma

```bash
# 0) Bağımlılıklar
pip install -r requirements-api.txt
cd web && npm install && cd ..

# 1) Güvenli .env (rastgele JWT secret, 600 yetkisi)
python scripts/gen_env.py
# .env içine MOMENZ_D1_* ve MOMENZ_GOOGLE_SERVICE_ACCOUNT_JSON gir

# 2) D1 şeması + ilk kullanıcı
python scripts/migrate.py
python scripts/bootstrap_admin.py admin@domain.com

# 3) Üç terminal
uvicorn api.main:app --reload --port 8000      # API  → :8000
cd web && cp .env.example .env.local && npm run dev   # Web  → :3000
python -m worker.index_job                     # Worker (job kuyruğu)
```

`http://localhost:3000` → giriş yap → klasör linki ekle → tarama bitince yüz yükle.

Not: Local'de `MOMENZ_ENVIRONMENT=dev` olduğu için doğrulama maili **sunucu
konsoluna** yazılır (`[DEV MAIL]` satırı). Token'ı oradan alıp
`/api/v1/auth/verify?token=...` çağırabilirsin. Bootstrap admin doğrulanmış
olarak oluşturulur, direkt giriş yapabilirsin.

Next.js, API'yi `/api/v1/*` altına proxy'ler (`web/next.config.ts`), yani
cookie'ler first-party kalır ve CSRF akışı sorunsuz çalışır.

## Prod'a alma

1. **D1 migration:** prod D1 bilgileriyle `.env` doldur, `python scripts/migrate.py`.
2. **Render API:** `New → Web Service` (veya Blueprint → `render.yaml`).
   Runtime **Docker**, plan **Free**, Health Check **`/health`**.
   `render.yaml` JWT secret'ı `generateValue: true` ile üretir,
   `COOKIE_SECURE=true` ve trusted host'ları ayarlar.
3. **Mail:** `MOMENZ_RESEND_API_KEY` mutlaka tanımla; yoksa kayıt olan kullanıcı
   e-postasını doğrulayamaz ve giriş yapamaz (bilinçli fail-closed).
4. **Keepalive:** `cd deploy && wrangler secret put RENDER_URL && wrangler deploy`.
5. **Worker:** `modal secret create momenz ...` ardından
   `modal deploy worker/index_job.py`. Secret'e `MOMENZ_D1_*` ve Google
   credential değerlerini gir.
6. **Web:** Vercel → `web/` klasörünü import et, `API_BACKEND_URL` = Render URL.
7. Render env'inde `MOMENZ_TRUSTED_HOSTS` ve `MOMENZ_CORS_ORIGINS` değerlerine
   gerçek Vercel domain'ini ekle.

Prod'da `MOMENZ_ENVIRONMENT=prod` ile birlikte şunlar **zorunlu**:
JWT secret ≥ 32 karakter rastgele değer, `COOKIE_SECURE=true`, açık
`TRUSTED_HOSTS`. Biri eksikse API açılışta reddedilir (`api/config.py`).
