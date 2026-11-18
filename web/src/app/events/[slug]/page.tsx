"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import FaceSearch from "@/components/FaceSearch";
import LoadingScreen from "@/components/LoadingScreen";
import { useAuth } from "@/components/AuthProvider";
import {
  ApiError,
  ensureCsrf,
  getEvent,
  getEventPhotos,
  joinEvent,
  leaveEvent,
} from "@/lib/api";
import type { Event, EventPhoto } from "@/lib/types";

export default function EventDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { me } = useAuth();
  const [event, setEvent] = useState<Event | null>(null);
  const [photos, setPhotos] = useState<EventPhoto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [lightbox, setLightbox] = useState<EventPhoto | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [item, gallery] = await Promise.all([
        getEvent(slug),
        getEventPhotos(slug, 8),
      ]);
      setEvent(item);
      setPhotos(gallery.items.slice(0, 8));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Etkinlik yüklenemedi.");
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void ensureCsrf();
  }, []);

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
      <nav className="breadcrumb" aria-label="Gezinme">
        <Link href="/">ETKİNLİKLER</Link>
        <span>/</span>
        <span>{event?.title || "YÜKLENİYOR"}</span>
      </nav>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert">{notice}</div>}

      {loading ? (
        <LoadingScreen label="ETKİNLİK YÜKLENİYOR" />
      ) : !event ? (
        <div className="empty-state">
          <div className="empty-mark">404</div>
          <h3>Etkinlik bulunamadı.</h3>
          <Link className="btn btn-primary" href="/">Etkinliklere dön</Link>
        </div>
      ) : (
        <div className="detail-layout">
          <div className="detail-main">
            <div className="detail-hero-strip">
              <div className="eyebrow">{event.date_label || "TARİH YAKINDA"}</div>
              <h1>{event.title}</h1>
              <div className="detail-strip-meta">
                <span>{event.image_count} FOTOĞRAF</span>
                <span>{event.face_count} YÜZ</span>
                <span>YÜZ TANIMA AKTİF</span>
              </div>
            </div>

            <FaceSearch folderKey={event.folder_key} />

            <section className="gallery-section">
              <div className="section-head compact">
                <div>
                  <div className="eyebrow">02 / FOTOĞRAFLAR</div>
                  <h2 className="section-title small">Etkinlikten kareler</h2>
                </div>
                <span className="meta">{photos.length} önizleme · {event.image_count} fotoğraf</span>
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
                      <img src={photo.thumb_url} alt={photo.name} />
                      <span className="photo-index">+</span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </div>

          <aside className="detail-aside">
            <div className="aside-card">
              <div className="aside-label">KATILIM</div>
              {event.is_owner ? (
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
                <div><dt>Drive yükleme</dt><dd>{event.date_label || "—"}</dd></div>
                <div>
                  <dt>Sisteme yükleme</dt>
                  <dd>
                    {event.created_at
                      ? new Date(event.created_at).toLocaleDateString("tr-TR")
                      : "—"}
                  </dd>
                </div>
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
            src={`${lightbox.thumb_url}${lightbox.thumb_url.includes("?") ? "&" : "?"}size=512`}
            alt={lightbox.name}
          />
          <div className="lightbox-caption">{lightbox.name} · ESC ile kapat</div>
        </div>
      )}
    </main>
  );
}
