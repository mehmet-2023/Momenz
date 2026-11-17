# Momenz — Topluluk fotoğraf arşivi

Etkinlikler herkese açık listelenir. Giriş yapan kullanıcılar kendi etkinliğini
ekler, katılımcı olarak katılır. Her etkinliğin Drive fotoğraf arşivinde yüz
eşleştirme yapılabilir.

## Yapı

```
web/ (Next.js, Vercel)  →  api/ (FastAPI, Render)  →  Cloudflare D1
                                  │
                          Modal index worker
```

- `api/routes/events.py` — public etkinlik listesi/detay/fotoğraflar, auth'lu
  ekleme ve katılım.
- `api/routes/public` — herkese açık fotoğraf thumbnail'leri.
- `api/routes/search.py` — public etkinliklerde girişsiz, özel klasörlerde
  auth'lu yüz arama.
- `migrations/0001_init.sql` — auth, çok kullanıcılılık, job kuyruğu.
- `migrations/0002_events.sql` — `events`, `event_attendees`, mevcut klasörlerin
  etkinliğe dönüştürülmesi.
- Tasarım: `docs/DESIGN.md` — siyah/beyaz, Space Mono, 1px kenarlık, köşe yok.

## Yeni sayfalar

| Sayfa | Açıklama |
|---|---|
| `/` | Etkinlik listesi, arama, kategori ve "yaklaşanlar" filtresi (public) |
| `/events/[slug]` | Etkinlik detayı, fotoğraf arşivi, yüz arama, katılım |
| `/events/new` | Yeni etkinlik (giriş gerekli), Drive klasörü + arka plan tarama |
| `/login`, `/register` | Cookie + CSRF tabanlı kimlik |

## Kurulum

```bash
pip install -r requirements-api.txt
python scripts/gen_env.py            # .env (600) + rastgele JWT secret
# .env: MOMENZ_D1_* ve MOMENZ_GOOGLE_SERVICE_ACCOUNT_JSON doldur
python scripts/migrate.py            # 0001 + 0002
python scripts/bootstrap_admin.py admin@domain.com

uvicorn api.main:app --reload --port 8000
cd web && npm install && npm run dev  # :3000, /api/v1 → :8000 proxy
python -m worker.index_job            # yerel index worker
```

Prod: `render.yaml` (Web Service, Docker, `/health`), Vercel Root Directory
`web/`, Cloudflare Worker keepalive, Modal worker. Ayrıntılar önceki runbook'ta.

Güvenlik: JWT secret rastgele, argon2id, httpOnly cookie + double-submit CSRF,
refresh token hash'lenerek saklanır, tüm D1 sorguları parametreli, `owner_id`
izolasyonu. `.env`, `credentials.json`, `.streamlit/secrets.toml` git'e girmez.
