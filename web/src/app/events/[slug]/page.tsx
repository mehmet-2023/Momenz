"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import FaceSearch from "@/components/FaceSearch";
import SiteHeader from "@/components/SiteHeader";
import {
  ApiError,
  auth,
  ensureCsrf,
  getEvent,
  getEventPhotos,
  joinEvent,
  leaveEvent,
} from "@/lib/api";
import type { Event, EventPhoto, User } from "@/lib/types";

export default function EventDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const [event, setEvent] = useState<Event | null>(null);
  const [photos, setPhotos] = useState<EventPhoto[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [item, gallery] = await Promise.all([
        getEvent(slug),
        getEventPhotos(slug),
      ]);
      setEvent(item);
      setPhotos(gallery.items);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Etkinlik yüklenemedi.");
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    void ensureCsrf();
    auth.me().then(setMe).catch(() => setMe(null));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggleJoin() {
    if (!event || !me) return;
    try {
      if (event.is_attending) await leaveEvent(event.slug);
      else await joinEvent(event.slug);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "İşlem başarısız.");
    }
  }

  return (
    <>
      <SiteHeader />
      <main className="container">
        {error && <div className="alert alert-error">{error}</div>}
        {loading ? (
          <p className="caption">Yükleniyor...</p>
        ) : !event ? (
          <div className="no-image">Etkinlik bulunamadı.</div>
        ) : (
          <>
            <section className="event-hero">
              {event.cover_url && (
                <img className="event-hero-cover" src={event.cover_url} alt="" />
              )}
              <div className="event-hero-body">
                <span className="event-date-badge">{event.date_label || "Tarih yakında"}</span>
                <h1>{event.title}</h1>
                <div className="event-meta-line">
                  <span>{event.location || "Konum belirtilmedi"}</span>
                  <span>{event.image_count} fotoğraf</span>
                  <span>{event.face_count} yüz</span>
                  <span>{event.attendee_count} katılımcı</span>
                </div>
                {event.description && <p className="event-desc">{event.description}</p>}
                <div className="event-actions">
                  {me ? (
                    <button className="btn" type="button" onClick={toggleJoin}>
                      {event.is_attending ? "Katılımı bırak" : "Etkinliğe katıl"}
                    </button>
                  ) : (
                    <Link className="btn" href="/login">Katılmak için giriş yap</Link>
                  )}
                  <Link className="btn" href="/">← Etkinlikler</Link>
                </div>
              </div>
            </section>

            <section>
              <div className="step-head">
                <div className="step-no">01</div>
                <div>
                  <div className="step-title">Fotoğraf arşivi</div>
                  <div className="step-desc">Bu etkinlikten {photos.length} fotoğraf önizlemesi.</div>
                </div>
              </div>
              {photos.length === 0 ? (
                <div className="no-image">Henüz fotoğraf yüklenmedi.</div>
              ) : (
                <div className="photo-grid">
                  {photos.map((photo) => (
                    <img key={photo.file_id} src={photo.thumb_url} alt={photo.name} loading="lazy" />
                  ))}
                </div>
              )}
            </section>

            <div className="rule" />
            <FaceSearch folderKey={event.folder_key} />
          </>
        )}

        <footer className="footer">
          <span>BY OCAL · MOMENZ</span>
          <span>Üçüncü taraf yüz tanıma servisi kullanılmaz · Sonuçları gözle doğrula</span>
        </footer>
      </main>
    </>
  );
}
