"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import EventCard from "@/components/EventCard";
import { useAuth } from "@/components/AuthProvider";
import { ApiError, listEvents } from "@/lib/api";
import type { Event } from "@/lib/types";

function useCountUp(target: number, duration = 900) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!target) {
      setValue(0);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return value;
}

function EventSkeleton() {
  return (
    <div className="event-card skeleton-card" aria-hidden="true">
      <div className="skeleton skeleton-cover" />
      <div className="event-card-body">
        <div className="skeleton skeleton-line short" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line medium" />
      </div>
    </div>
  );
}

export default function Home() {
  const { me, loading: authLoading } = useAuth();
  const [events, setEvents] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [upcoming, setUpcoming] = useState(false);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listEvents({ upcoming, q: query || undefined, limit: 60 });
      setEvents(data.items);
      setTotal(data.total);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Etkinlikler yüklenemedi.");
    } finally {
      setLoading(false);
    }
  }, [upcoming, query]);

  useEffect(() => {
    void load();
  }, [load]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setQuery(search.trim());
  }

  const { photoCount, faceCount, attendeeCount } = useMemo(
    () =>
      events.reduce(
        (acc, item) => ({
          photoCount: acc.photoCount + item.image_count,
          faceCount: acc.faceCount + item.face_count,
          attendeeCount: acc.attendeeCount + item.attendee_count,
        }),
        { photoCount: 0, faceCount: 0, attendeeCount: 0 },
      ),
    [events],
  );

  const shownPhotos = useCountUp(photoCount);
  const shownFaces = useCountUp(faceCount);
  const shownTotal = useCountUp(total);

  const [featured, ...rest] = events;

  return (
    <main>
      {/* ------------------------------------------------------------- HERO */}
      <section className="hero">
        <div className="hero-grid" aria-hidden="true" />
        <div className="hero-inner">
          <div className="hero-eyebrow reveal" style={{ animationDelay: "0ms" }}>
            <span className="live-dot" /> TOPLULUK FOTOĞRAF ARŞİVİ · 2026
          </div>

          <h1 className="hero-title">
            <span className="hero-line reveal" style={{ animationDelay: "80ms" }}>
              Fotoğrafların
            </span>
            <span className="hero-line reveal" style={{ animationDelay: "180ms" }}>
              içinde <em>kendini bul.</em>
            </span>
          </h1>

          <p className="hero-lead reveal" style={{ animationDelay: "300ms" }}>
            Momenz, etkinliklerin fotoğraflarını tek bir arşivde toplayan bir
            topluluk platformu. Etkinlikleri keşfet, arşivde gezin, yüzünü yükle;
            senin olan kareleri saniyeler içinde bulalım. Üçüncü taraf yüz tanıma
            servisi yok, verilerin saklanmaz.
          </p>

          <div className="hero-actions reveal" style={{ animationDelay: "400ms" }}>
            <a className="btn btn-light" href="#etkinlikler">
              Etkinlikleri keşfet <span aria-hidden="true">↓</span>
            </a>
            {!authLoading &&
              (me ? (
                <Link className="btn btn-ghost-light" href="/events/new">
                  + Etkinlik ekle
                </Link>
              ) : (
                <Link className="btn btn-ghost-light" href="/register">
                  Üye ol, arşive katıl
                </Link>
              ))}
          </div>

          <div className="hero-stats reveal" style={{ animationDelay: "520ms" }}>
            <div className="hero-stat">
              <b>{shownTotal}</b>
              <span>Etkinlik</span>
            </div>
            <div className="hero-stat">
              <b>{shownPhotos}</b>
              <span>Fotoğraf</span>
            </div>
            <div className="hero-stat">
              <b>{shownFaces}</b>
              <span>Tespit edilen yüz</span>
            </div>
            <div className="hero-stat">
              <b>{attendeeCount}</b>
              <span>Katılımcı</span>
            </div>
          </div>
        </div>

        <div className="ticker" aria-hidden="true">
          <div className="ticker-track">
            {Array.from({ length: 4 }).map((_, i) => (
              <span key={i}>
                ETKİNLİKLER <i>✳</i> FOTOĞRAFLAR <i>✳</i> YÜZ EŞLEŞTİRME <i>✳</i>{" "}
                TOPLULUK <i>✳</i>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- ETKİNLİKLER */}
      <section className="container events-section" id="etkinlikler">
        <div className="section-head">
          <div>
            <div className="eyebrow">01 / ARŞİV</div>
            <h2 className="section-title">Etkinlikler</h2>
          </div>
          <p className="section-lead">
            Her etkinlik kendi fotoğraf arşiviyle gelir. Birine katıl, kapak
            fotoğraflarına göz at ve içinde kendi yüzünü ara.
          </p>
        </div>

        <div className="toolbar">
          <form className="toolbar-search" onSubmit={submitSearch}>
            <span className="toolbar-prefix" aria-hidden="true">/</span>
            <input
              className="toolbar-input"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Etkinlik veya konum ara..."
              aria-label="Etkinlik ara"
            />
            <button className="btn" type="submit">ARA</button>
          </form>
          <button
            type="button"
            className={`chip${upcoming ? " active" : ""}`}
            onClick={() => setUpcoming((value) => !value)}
            aria-pressed={upcoming}
          >
            {upcoming ? "● Yaklaşanlar" : "○ Yaklaşanlar"}
          </button>
          <div className="view-toggle" role="group" aria-label="Görünüm">
            <button
              type="button"
              className={view === "grid" ? "active" : ""}
              onClick={() => setView("grid")}
              aria-label="Izgara görünümü"
            >
              ▦
            </button>
            <button
              type="button"
              className={view === "list" ? "active" : ""}
              onClick={() => setView("list")}
              aria-label="Liste görünümü"
            >
              ☰
            </button>
          </div>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        {loading ? (
          <div className="event-grid">
            {Array.from({ length: 6 }).map((_, i) => (
              <EventSkeleton key={i} />
            ))}
          </div>
        ) : events.length === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">∅</div>
            <h3>{query ? "Sonuç bulunamadı." : "Arşiv henüz boş."}</h3>
            <p>
              {query
                ? "Farklı bir arama deneyebilirsin."
                : "İlk etkinliği ekleyerek topluluk arşivini başlatabilirsin."}
            </p>
            {me && !query && (
              <Link className="btn btn-primary" href="/events/new">
                + İlk etkinliği ekle
              </Link>
            )}
          </div>
        ) : (
          <>
            {!query && !upcoming && featured && (
              <Link className="featured" href={`/events/${featured.slug}`}>
                <div className="featured-media">
                  {featured.cover_url ? (
                    <img src={featured.cover_url} alt="" loading="lazy" />
                  ) : (
                    <div className="featured-placeholder">KAPAK YOK</div>
                  )}
                  <span className="featured-tag">ÖNE ÇIKAN</span>
                </div>
                <div className="featured-body">
                  <div className="eyebrow">{featured.date_label || "TARİH YAKINDA"}</div>
                  <h3>{featured.title}</h3>
                  {featured.description && (
                    <p>{featured.description}</p>
                  )}
                  <div className="featured-meta">
                    <span>{featured.image_count} FOTOĞRAF</span>
                    <span>{featured.face_count} YÜZ</span>
                    <span>{featured.attendee_count} KATILIMCI</span>
                    <span className="featured-cta">ARŞİVİ AÇ →</span>
                  </div>
                </div>
              </Link>
            )}

            {rest.length > 0 && (
              <div className="list-head">
                <span>{query ? `"${query}" İÇİN SONUÇLAR` : "TÜM ETKİNLİKLER"}</span>
                <span>{String(rest.length).padStart(2, "0")} KAYIT</span>
              </div>
            )}

            <div className={view === "grid" ? "event-grid" : "event-list"}>
              {(query || upcoming ? events : rest).map((event) => (
                <EventCard key={event.id} event={event} view={view} />
              ))}
            </div>
          </>
        )}

        <div className="bottom-cta">
          <div>
            <div className="eyebrow">SENİN ETKİNLİĞİN</div>
            <h3>Fotoğrafların bir araya gelsin.</h3>
            <p>Drive klasörünü bağla, yüz taramasını arka planda çalıştır, arşivi toplulukla paylaş.</p>
          </div>
          <Link className="btn btn-primary" href={me ? "/events/new" : "/register"}>
            {me ? "+ Etkinlik ekle" : "Üye ol ve başla"}
          </Link>
        </div>
      </section>
    </main>
  );
}
