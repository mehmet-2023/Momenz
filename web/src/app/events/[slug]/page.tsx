"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import FaceSearch from "@/components/FaceSearch";
import { useAuth } from "@/components/AuthProvider";
import {
  ApiError,
  auth,
  ensureCsrf,
  getEvent,
  getEventPhotos,
  joinEvent,
  leaveEvent,
} from "@/lib/api";
import { DEMO_EVENT, DEMO_PHOTOS } from "@/lib/demo";
import type { Event, EventPhoto } from "@/lib/types";

export default function EventDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const isDemo = slug === DEMO_EVENT.slug;
  const { me, setMe } = useAuth();
  const [event, setEvent] = useState<Event | null>(null);
  const [photos, setPhotos] = useState<EventPhoto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [lightbox, setLightbox] = useState<EventPhoto | null>(null);

  const load = useCallback(async () => {
    // ⚠️ TEST: geçici demo etkinliği API'ye gitmeden yerel veriden göster.
    if (isDemo) {
      setEvent(DEMO_EVENT);
      setPhotos(DEMO_PHOTOS);
      setError("");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [item, gallery] = await Promise.all([
        getEvent(slug),
        getEventPhotos(slug, 40),
      ]);
      setEvent(item);
      setPhotos(gallery.items);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Etkinlik yüklenemedi.");
    } finally {
      setLoading(false);
    }
  }, [slug, isDemo]);

  useEffect(() => {
    void ensureCsrf();
    void auth.me().then(setMe).catch(() => setMe(null));
  }, [setMe]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!lightbox) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setLightbox(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox]);

  async function toggleJoin() {
    if (!event) return;
    setBusy(true);
    setNotice("");
    try {
      if (event.is_attending) {
        await leaveEvent(event.slug);
        setNotice("Etkinlikten ayrıldın.");
      } else {
        await joinEvent(event.slug);
        setNotice("Etkinliğe katıldın. Fotoğraflar artık senin de.");
      }
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "İşlem başarısız.");
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setNotice("Bağlantı kopyalandı.");
    } catch {
      setNotice("Bağlantı kopyalanamadı.");
    }
  }

  return (
    <main className="container detail-page">
      <nav className="breadcrumb" aria-label="Konum">
        <Link href="/">ETKİNLİKLER</Link>
        <span>/</span>
        <span>{event?.title || "YÜKLENİYOR"}</span>
      </nav>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert">{notice}</div>}

      {loading ? (
        <div className="detail-skeleton">
          <div className="skeleton skeleton-hero" />
          <div className="skeleton skeleton-line" />
        </div>
      ) : !event ? (
        <div className="empty-state">
          <div className="empty-mark">404</div>
          <h3>Etkinlik bulunamadı.</h3>
          <Link className="btn btn-primary" href="/">Etkinliklere dön</Link>
        </div>
      ) : (
        <div className="detail-layout">
          <div className="detail-main">
            <div className="detail-cover">
              {event.cover_url ? (
                <img src={event.cover_url} alt="" />
              ) : (
                <div className="detail-cover-empty">BU ETKİNLİĞİN KAPAĞI YOK</div>
              )}
            </div>

            <div className="detail-heading">
              <div className="eyebrow">{event.date_label || "TARİH YAKINDA"}</div>
              <h1>{event.title}</h1>
              {event.location && (
                <div className="detail-location">⌖ {event.location}</div>
              )}
              {event.description && (
                <p className="detail-desc">{event.description}</p>
              )}
            </div>

            <section className="gallery-section">
              <div className="section-head compact">
                <div>
                  <div className="eyebrow">01 / FOTOĞRAFLAR</div>
                  <h2 className="section-title small">Etkinlikten kareler</h2>
                </div>
                <span className="meta">{photos.length} önizleme</span>
              </div>
              {photos.length === 0 ? (
                <div className="no-image">Henüz fotoğraf yüklenmedi. Tarama tamamlandığında burada görünecek.</div>
              ) : (
                <div className="photo-grid">
                  {photos.map((photo) => (
                    <button
                      key={photo.file_id}
                      type="button"
                      className="photo-tile"
                      onClick={() => setLightbox(photo)}
                      aria-label={`${photo.name} fotoğrafını büyüt`}
                    >
                      <img src={photo.thumb_url} alt={photo.name} loading="lazy" />
                      <span className="photo-index">+</span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <div className="rule" />
            <FaceSearch folderKey={event.folder_key} />
          </div>

          <aside className="detail-aside">
            <div className="aside-card">
              <div className="aside-label">KATILIM</div>
              {isDemo ? (
                <div className="aside-owner">Bu bir test etkinliğidir. Katılım devre dışı.</div>
              ) : event.is_owner ? (
                <div className="aside-owner">Bu etkinliği sen ekledin.</div>
              ) : me ? (
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={toggleJoin}
                  disabled={busy}
                >
                  {busy
                    ? "İşleniyor..."
                    : event.is_attending
                      ? "Katılımı bırak"
                      : "Etkinliğe katıl"}
                </button>
              ) : (
                <Link className="btn btn-primary" href="/login">
                  Katılmak için giriş yap
                </Link>
              )}
              <div className="aside-attendees">
                <b>{event.attendee_count}</b> katılımcı
              </div>
            </div>

            <div className="aside-card">
              <div className="aside-label">ETKİNLİK BİLGİLERİ</div>
              <dl className="fact-list">
                <div><dt>Tarih</dt><dd>{event.date_label || "—"}</dd></div>
                <div><dt>Konum</dt><dd>{event.location || "—"}</dd></div>
                <div><dt>Fotoğraf</dt><dd>{event.image_count}</dd></div>
                <div><dt>Yüz</dt><dd>{event.face_count}</dd></div>
                <div><dt>Ekleyen</dt><dd>{event.is_owner ? "Sen" : "Topluluk"}</dd></div>
              </dl>
            </div>

            <div className="aside-card">
              <div className="aside-label">PAYLAŞ</div>
              <button className="btn" type="button" onClick={copyLink} style={{ width: "100%" }}>
                Bağlantıyı kopyala
              </button>
              <p className="aside-note">
                Etkinlik herkese açık. Bağlantıyı paylaşarak daha fazla kişinin kendi fotoğrafını bulmasını sağla.
              </p>
            </div>
          </aside>
        </div>
      )}

      {lightbox && (
        <div className="lightbox" role="dialog" aria-modal="true" onClick={() => setLightbox(null)}>
          <button className="lightbox-close" type="button" onClick={() => setLightbox(null)} aria-label="Kapat">
            ✕
          </button>
          <img
            src={`${lightbox.thumb_url}${lightbox.thumb_url.includes("?") ? "&" : "?"}size=1024`}
            alt={lightbox.name}
          />
          <div className="lightbox-caption">{lightbox.name} · ESC ile kapat</div>
        </div>
      )}
    </main>
  );
}
