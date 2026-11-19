"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import EventReminder from "@/components/EventReminder";
import FaceSearch from "@/components/FaceSearch";
import LoadingScreen from "@/components/LoadingScreen";
import {
  ApiError,
  attachEventDrive,
  createFolder,
  ensureCsrf,
  getEvent,
  getEventPhotos,
  getJob,
  listFolders,
} from "@/lib/api";
import type { Event, EventPhoto, Job } from "@/lib/types";

const TERMINAL = ["done", "failed", "canceled"];

export default function EventDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const [event, setEvent] = useState<Event | null>(null);
  const [photos, setPhotos] = useState<EventPhoto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [lightbox, setLightbox] = useState<EventPhoto | null>(null);
  const [driveUrl, setDriveUrl] = useState("");
  const [attachUrl, setAttachUrl] = useState("");
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateJob, setUpdateJob] = useState<Job | null>(null);

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
      if (item.is_owner) {
        try {
          const folders = await listFolders();
          setDriveUrl(
            folders.find((folder) => folder.key === item.folder_key)?.url ?? "",
          );
        } catch {
          setDriveUrl("");
        }
      }
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
    const title = window.sessionStorage.getItem("momenz:existing-event");
    if (title) {
      window.sessionStorage.removeItem("momenz:existing-event");
      setError(
        `Bu Drive klasörü zaten “${title}” etkinliği olarak kayıtlı. Yeni etkinlik oluşturulmadı.`,
      );
    }
  }, []);

  useEffect(() => {
    if (!updateJob || TERMINAL.includes(updateJob.status)) return;
    let alive = true;
    const timer = window.setInterval(async () => {
      try {
        const current = await getJob(updateJob.id);
        if (!alive) return;
        setUpdateJob(current);
        if (TERMINAL.includes(current.status)) {
          setNotice(
            current.status === "done"
              ? "Yeni fotoğraflar indexlendi. Etkinlik güncellendi."
              : "Drive güncellemesi tamamlanamadı.",
          );
          if (current.status === "done") void load();
        }
      } catch {
      }
    }, 4000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [updateJob?.id, updateJob?.status, load]); 

  useEffect(() => {
    if (!lightbox) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setLightbox(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox]);

  async function refreshDrive() {
    if (!driveUrl) {
      setNotice("Drive bağlantısı bulunamadı.");
      return;
    }
    setUpdateBusy(true);
    setNotice("");
    try {
      const { jobId } = await createFolder(driveUrl);
      if (!jobId) throw new Error("İş başlatılamadı.");
      setUpdateJob(await getJob(jobId));
      setNotice("Drive taranıyor. Yeni fotoğraflar sırayla eklenecek.");
    } catch (cause) {
      setNotice(
        cause instanceof ApiError ? cause.message : "Drive güncellemesi başlatılamadı.",
      );
    } finally {
      setUpdateBusy(false);
    }
  }

  async function attachDrive(e: FormEvent) {
    e.preventDefault();
    const clean = attachUrl.trim();
    if (!clean) return;
    setUpdateBusy(true);
    setNotice("");
    try {
      const { event: updated, jobId } = await attachEventDrive(slug, clean);
      setEvent(updated);
      setAttachUrl("");
      if (jobId) setUpdateJob(await getJob(jobId));
      setNotice("Drive bağlandı. Fotoğraflar sırayla taranacak.");
    } catch (cause) {
      setNotice(
        cause instanceof ApiError
          ? cause.message
          : "Drive bağlanamadı. Linki kontrol edip tekrar dene.",
      );
    } finally {
      setUpdateBusy(false);
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
      <nav className="breadcrumb init-seq" aria-label="Gezinme">
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
            <div className="detail-hero-strip init-seq">
              <div className="eyebrow">{event.date_label || "TARİH YAKINDA"}</div>
              <h1>{event.title}</h1>
              {event.description && (
                <p className="detail-desc">{event.description}</p>
              )}
              <div className="detail-strip-meta">
                <span>{event.image_count} FOTOĞRAF</span>
                <span>{event.face_count} YÜZ</span>
                <span>
                  {event.drive_pending
                    ? "DRIVE BEKLENİYOR"
                    : event.image_count > 0
                      ? "YÜZ TANIMA AKTİF"
                      : "TARAMA SÜRÜYOR"}
                </span>
              </div>
            </div>

            {event.image_count > 0 ? (
              <FaceSearch folderKey={event.folder_key} />
            ) : (
              <section className="pending-panel init-seq">
                <div className="eyebrow">
                  {event.drive_pending ? "01 / HATIRLATMA" : "01 / HAZIRLANIYOR"}
                </div>
                <h2 className="pending-title">
                  {event.drive_pending
                    ? "Fotoğraflar henüz yüklenmedi."
                    : "Fotoğraflar hazırlanıyor."}
                </h2>
                <p className="pending-lead">
                  {event.drive_pending
                    ? "Drive klasörü bağlandığında tüm kareler taranacak ve yüzünü arayabileceksin. Hazır olduğunda haber vermemizi istersen e-postanı bırak."
                    : "Drive klasörü bağlı; yüz tanıma sırası devam ediyor. Bitince bu sayfa otomatik olarak açılacak."}
                </p>
                <EventReminder
                  slug={event.slug}
                  waiting={event.is_owner ? event.reminder_count : 0}
                />
              </section>
            )}

            <section className="gallery-section init-seq">
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
                <div className="photo-grid init-seq">
                  {photos.map((photo) => (
                    <button
                      key={photo.file_id}
                      type="button"
                      className="photo-tile"
                      onClick={() => setLightbox(photo)}
                      aria-label={`${photo.name} fotoğrafını büyüt`}
                    >
                      <img
                        src={photo.thumb_url}
                        alt={photo.name}
                        loading="lazy"
                        decoding="async"
                      />
                      <span className="photo-index">+</span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </div>

          <aside className="detail-aside init-seq">
            {event.is_owner && event.drive_pending && (
              <div className="aside-card">
                <div className="aside-label">DRIVE'I BAĞLA</div>
                <p className="aside-note">
                  Fotoğraflar hazır olduğunda klasör linkini buradan ekle.
                  Tarama hemen başlar; sayfa kendini günceller.
                </p>
                <form className="attach-form" onSubmit={attachDrive}>
                  <input
                    className="input"
                    type="url"
                    required
                    placeholder="https://drive.google.com/drive/folders/..."
                    value={attachUrl}
                    onChange={(e) => setAttachUrl(e.target.value)}
                    aria-label="Drive klasör linki"
                  />
                  <button
                    className="btn btn-primary"
                    type="submit"
                    disabled={updateBusy || !attachUrl.trim()}
                    style={{ width: "100%" }}
                  >
                    {updateBusy ? "Bağlanıyor..." : "Drive'ı bağla"}
                  </button>
                </form>
              </div>
            )}

            {event.is_owner && !event.drive_pending && (
              <div className="aside-card">
                <div className="aside-label">DRIVE'I GÜNCELLE</div>
                <p className="aside-note">
                  Klasöre sonradan eklenen fotoğraflar taranır. Zaten indexlenen
                  kareler yeniden işlenmez.
                </p>
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={refreshDrive}
                  disabled={
                    updateBusy ||
                    !driveUrl ||
                    (!!updateJob && !TERMINAL.includes(updateJob.status))
                  }
                  style={{ width: "100%" }}
                >
                  {updateBusy
                    ? "Başlatılıyor..."
                    : updateJob && !TERMINAL.includes(updateJob.status)
                      ? "Taranıyor..."
                      : "Drive'ı güncelle"}
                </button>
                {updateJob && (
                  <div className="meta">
                    {updateJob.status.toUpperCase()} · %{Math.round(updateJob.progress * 100)}
                    <div className="progress">
                      <span style={{ width: `${Math.round(updateJob.progress * 100)}%` }} />
                    </div>
                  </div>
                )}
              </div>
            )}

            {event.is_owner && event.reminder_count > 0 && (
              <div className="aside-card">
                <div className="aside-label">HATIRLATMA LİSTESİ</div>
                <div className="reminder-total">{event.reminder_count}</div>
                <p className="aside-note">
                  kişi fotoğraflar yüklendiğinde haber verilmesini bekliyor.
                  Drive bağlanıp tarama bitince tek seferlik e-posta gider.
                </p>
              </div>
            )}

            <div className="aside-card">
              <div className="aside-label">ETKİNLİK BİLGİLERİ</div>
              <dl className="fact-list">
                <div><dt>Tarih</dt><dd>{event.date_label || "—"}</dd></div>
                <div>
                  <dt>Drive yükleme</dt>
                  <dd>
                    {event.drive_pending
                      ? "Henüz yüklenmedi"
                      : event.date_label || "—"}
                  </dd>
                </div>
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
