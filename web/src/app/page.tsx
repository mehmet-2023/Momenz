"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import EventCard from "@/components/EventCard";
import SiteHeader from "@/components/SiteHeader";
import { ApiError, ensureCsrf, listEvents } from "@/lib/api";
import type { Event } from "@/lib/types";

const CATEGORIES = ["tumu", "diger", "muzik", "spor", "sergi", "kampus", "topluluk"];

export default function Home() {
  const [events, setEvents] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [category, setCategory] = useState("tumu");
  const [upcoming, setUpcoming] = useState(false);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listEvents({
        category,
        upcoming,
        q: query || undefined,
        limit: 60,
      });
      setEvents(data.items);
      setTotal(data.total);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Etkinlikler yüklenemedi.");
    } finally {
      setLoading(false);
    }
  }, [category, upcoming, query]);

  useEffect(() => {
    void ensureCsrf();
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setQuery(search.trim());
  }

  const totalPhotos = events.reduce((sum, item) => sum + item.image_count, 0);
  const totalFaces = events.reduce((sum, item) => sum + item.face_count, 0);

  return (
    <>
      <SiteHeader />

      <main className="container">
        <section className="page-intro">
          <div className="eyebrow">TOPLULUK FOTOĞRAF ARŞİVİ</div>
          <h1 className="page-title">Etkinlikler</h1>
          <p className="page-lead">
            Etkinlikleri keşfet, fotoğraf arşivine göz at ve kendi fotoğrafını bul.
            Hesabın varsa etkinlik ekleyebilir ve katılımcılara katılabilirsin.
          </p>
          <div className="stat-row">
            <div className="stat"><b>{total}</b><span>Etkinlik</span></div>
            <div className="stat"><b>{totalPhotos}</b><span>Fotoğraf</span></div>
            <div className="stat"><b>{totalFaces}</b><span>Tespit edilen yüz</span></div>
          </div>
        </section>

        <div className="filter-bar">
          <form onSubmit={submitSearch} style={{ display: "flex", gap: 8, flex: 1 }}>
            <input
              className="input"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Etkinlik veya konum ara..."
              aria-label="Etkinlik ara"
            />
            <button className="btn" type="submit">Ara</button>
          </form>
          <button
            type="button"
            className={`chip${upcoming ? " active" : ""}`}
            onClick={() => setUpcoming((value) => !value)}
          >
            Yaklaşanlar
          </button>
        </div>

        <div className="filter-bar">
          {CATEGORIES.map((item) => (
            <button
              key={item}
              type="button"
              className={`chip${category === item ? " active" : ""}`}
              onClick={() => setCategory(item)}
            >
              {item === "tumu" ? "Tümü" : item}
            </button>
          ))}
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        {loading ? (
          <p className="caption">Yükleniyor...</p>
        ) : events.length === 0 ? (
          <div className="no-image">
            Henüz etkinlik yok. Giriş yapıp ilk etkinliği sen ekle.
          </div>
        ) : (
          <div className="event-grid">
            {events.map((event) => (
              <EventCard key={event.id} event={event} />
            ))}
          </div>
        )}

        <div style={{ marginTop: 32 }}>
          <Link className="btn" href="/events/new">+ Yeni etkinlik ekle</Link>
        </div>

        <footer className="footer">
          <span>BY OCAL · MOMENZ</span>
          <span>Üçüncü taraf yüz tanıma servisi kullanılmaz · Sonuçları gözle doğrula</span>
        </footer>
      </main>
    </>
  );
}
