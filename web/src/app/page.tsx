"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent,
} from "react";
import EventCard from "@/components/EventCard";
import HeroBackdrop from "@/components/HeroBackdrop";
import { useAuth } from "@/components/AuthProvider";
import { ApiError, listEvents } from "@/lib/api";
import type { Event } from "@/lib/types";

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
  const heroRef = useRef<HTMLElement>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listEvents({ q: query || undefined, limit: 60 });
      setEvents(data.items);
    } catch (cause) {
      setEvents([]);
      if (cause instanceof ApiError && cause.status >= 500) {
        setError(cause.message);
      }
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setQuery(search.trim());
  }

  function onHeroMove(event: MouseEvent<HTMLElement>) {
    const el = heroRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    el.style.setProperty("--mx", ((x / rect.width - 0.5) * 2).toFixed(3));
    el.style.setProperty("--my", ((y / rect.height - 0.5) * 2).toFixed(3));
  }

  function onHeroLeave() {
    const el = heroRef.current;
    if (!el) return;
    el.style.setProperty("--mx", "0");
    el.style.setProperty("--my", "0");
  }

  const selfFindHref = events[0] ? `/events/${events[0].slug}` : "/events/new";

  const [featured, ...rest] = events;

  return (
    <main>
      {/* ------------------------------------------------------------- HERO */}
      <section
        className="hero hero-init"
        ref={heroRef}
        onMouseMove={onHeroMove}
        onMouseLeave={onHeroLeave}
      >
        <HeroBackdrop />

        <div className="hero-inner">
          <h1 className="hero-title">
            <span className="hero-line">Binlerce fotoğrafın</span>
            <span className="hero-line">içinde <em>kendini bul.</em></span>
          </h1>

          <p className="hero-lead">
            Etkinliğini seç, yüzünü yükle. Sana ait kareler sırayla gelsin.
          </p>

          <div className="hero-actions">
            <Link className="btn btn-light" href={selfFindHref}>
              <span aria-hidden="true">⌖</span> Kendini Bul
            </Link>
            <a className="btn btn-ghost-light" href="#etkinlikler">
              Etkinlikleri keşfet <span aria-hidden="true">↓</span>
            </a>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- ETKİNLİKLER */}
      <section className="container events-section" id="etkinlikler">
        <div className="section-head">
          <div>
            <div className="eyebrow">01 / ETKİNLİKLER</div>
            <h2 className="section-title">Etkinlikler</h2>
          </div>
          <p className="section-lead">
            Etkinlikleri keşfet, çekilen fotoğraflar arasında yüzünü ara. Her
            etkinlikte binlerce kare olabilir; Momenz sana ait olanları ayıklar.
          </p>
        </div>

        <div className="toolbar">
          <form className="toolbar-search" onSubmit={submitSearch}>
            <span className="toolbar-prefix" aria-hidden="true">/</span>
            <input
              className="toolbar-input"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Etkinlik ara..."
              aria-label="Etkinlik ara"
            />
            <button className="btn" type="submit">ARA</button>
          </form>
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
            <h3>{query ? "Sonuç bulunamadı." : "Henüz etkinlik yok."}</h3>
            <p>
              {query
                ? "Farklı bir arama deneyebilirsin."
                : "İlk etkinliği ekleyerek yüz tanımayı deneyebilirsin."}
            </p>
            {me && !query && (
              <Link className="btn btn-primary" href="/events/new">
                + İlk etkinliği ekle
              </Link>
            )}
          </div>
        ) : (
          <>
            {!query && featured && (
              <Link className="featured" href={`/events/${featured.slug}`}>
                <div className="featured-media">
                  {featured.cover_url ? (
                    <img src={featured.cover_url} alt="" />
                  ) : (
                    <div className="featured-placeholder">KAPAK YOK</div>
                  )}
                  <span className="featured-tag">ETKİNLİK</span>
                </div>
                <div className="featured-body">
                  <div className="eyebrow">{featured.date_label || "TARİH YAKINDA"}</div>
                  <h3>{featured.title}</h3>
                  {featured.description && <p>{featured.description}</p>}
                  <div className="featured-meta">
                    <span>{featured.image_count} FOTOĞRAF</span>
                    <span>{featured.face_count} YÜZ</span>
                    <span className="featured-cta">KENDİNİ BUL →</span>
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
              {(query ? events : rest).map((event) => (
                <EventCard key={event.id} event={event} view={view} />
              ))}
            </div>
          </>
        )}

        <div className="bottom-cta">
          <div>
            <div className="eyebrow">SENİN ETKİNLİĞİN</div>
            <h3>Etkinliğini yayınla.</h3>
            <p>
              Fotoğrafların bulunduğu klasörü bağla, yüz tanımayı arka planda
              çalıştır; herkes kendi fotoğraflarını kolayca bulsun.
            </p>
          </div>
          <Link className="btn btn-primary" href={me ? "/events/new" : "/register"}>
            {me ? "+ Etkinlik ekle" : "Üye ol ve etkinlik ekle"}
          </Link>
        </div>
      </section>
    </main>
  );
}
