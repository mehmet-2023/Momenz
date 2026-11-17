# Momenz — Topluluk fotoğraf arşivi

Etkinlikler herkese açık listelenir. Giriş yapan kullanıcılar kendi etkinliğini
ekler, katılımcı olarak katılır. Her etkinliğin Drive fotoğraf arşivinde yüz
eşleştirme yapılabilir. **Tek etkinlik türü vardır; kategori yoktur.**

## Canlı adresler

| Katman | URL |
|---|---|
| Web (Next.js, Vercel) | https://momenz.vercel.app |
| API (FastAPI, Render) | https://momenz.onrender.app |

Frontend, `/api/v1/*` isteklerini Next.js rewrite ile API'ye proxy'ler;
cookie'ler first-party kalır, CSRF çalışır.

## Yapı

```
web/ (Next.js)  →  api/ (FastAPI)  →  Cloudflare D1
  Vercel              Render             (source of truth)
                        │
                  Modal index worker
```

- `api/routes/events.py` — public etkinlik listesi/detay/fotoğraflar, auth'lu
  ekleme ve katılım.
- `api/routes/public` — herkese açık fotoğraf thumbnail'leri.
- `api/routes/search.py` — public etkinliklerde girişsiz yüz arama.
- `migrations/0001_init.sql` — auth, çok kullanıcılılık, job kuyruğu.
- `migrations/0002_events.sql` — `events`, `event_attendees`, mevcut klasörlerin
  etkinliğe dönüştürülmesi.
- Tasarım: `docs/DESIGN.md` — siyah/beyaz, Space Mono, 1px kenarlık, köşe yok,
  ölçülü animasyonlar.

## Sayfalar

| Sayfa | Açıklama |
|---|---|
| `/` | Animasyonlu hero + proje anlatımı; altında etkinlik arşivi, arama, kapaklar, fotoğraf/yüz/katılımcı sayıları, öne çıkan etkinlik, ızgara/liste görünümü |
| `/events/[slug]` | Etkinlik detayı, fotoğraf galerisi (lightbox), sticky bilgi paneli, katılım, yüz arama |
| `/events/new` | Girişli etkinlik oluşturma, Drive klasörü + arka plan tarama |
| `/login`, `/register` | Uygulama kabuğuna bağlı, tek tıkla ana sayfaya dönen kimlik ekranları |
| `/sifre-sifirla` | **Yalnızca mail akışı:** e-posta ile bağlantı isteme / yeni şifre belirleme |

## Kimlik ve mail

- Kayıt anında hesap kullanıma açılır; **e-posta doğrulaması yoktur.**
- Resend yalnızca "şifremi unuttum" akışında kullanılır.
- httpOnly access/refresh cookie + double-submit CSRF; argon2id parola hash'i;
  refresh token hash'lenerek saklanır ve rotation/reuse detection uygulanır.
- Prod env zorunlulukları: güçlü `MOMENZ_JWT_SECRET`,
  `MOMENZ_COOKIE_SECURE=true`, açık `MOMENZ_TRUSTED_HOSTS`.

## Yerel geliştirme

```bash
pip install -r requirements-api.txt
python scripts/gen_env.py            # .env (600) + rastgele JWT secret
# .env: MOMENZ_D1_* ve MOMENZ_GOOGLE_SERVICE_ACCOUNT_JSON doldur
python scripts/migrate.py            # 0001 + 0002
python scripts/bootstrap_admin.py admin@domain.com

uvicorn api.main:app --reload --port 8000
cd web && npm install && npm run dev  # :3000
# yerelde API için web/.env.local: API_BACKEND_URL=http://localhost:8000
python -m worker.index_job            # index worker
```

## Prod

- `render.yaml` — Web Service, Docker, Free, `/health`.
- Vercel — Root Directory `web/`, `API_BACKEND_URL` varsayılanı prod API'sini
  gösterir (need override yok).
- `deploy/keepalive-worker.js` — Cloudflare Worker Cron, `/health` ping'i.
- `MOMENZ_RESEND_API_KEY` Render dashboard'da tanımlı olmalı.
- `.env`, `credentials.json`, `.streamlit/secrets.toml` git'e girmez.
