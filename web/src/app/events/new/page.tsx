"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ApiError, createEvent, ensureCsrf, getJob } from "@/lib/api";
import type { Job } from "@/lib/types";

export default function NewEventPage() {
  const router = useRouter();
  const { me, loading: authLoading } = useAuth();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [url, setUrl] = useState("");
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureCsrf();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { event: created, jobId } = await createEvent({
        title,
        description,
        location,
        event_date: eventDate || undefined,
        url,
        include_subfolders: includeSubfolders,
      });
      if (jobId) {
        const initial = await getJob(jobId);
        setJob(initial);
        void (async () => {
          for (let i = 0; i < 180; i++) {
            await new Promise((resolve) => setTimeout(resolve, 2000));
            try {
              const current = await getJob(jobId);
              setJob(current);
              if (["done", "failed", "canceled"].includes(current.status)) break;
            } catch {
              // geçici ağ hatası
            }
          }
        })();
      }
      router.push(`/events/${created.slug}`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Etkinlik oluşturulamadı.");
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) {
    return <main className="container page-pad"><p className="caption">Yükleniyor...</p></main>;
  }

  if (!me) {
    return (
      <main className="container page-pad">
        <div className="empty-state">
          <div className="empty-mark">↗</div>
          <h3>Etkinlik eklemek için giriş yap.</h3>
          <p>Hesabınla arşive etkinlik ekleyebilir, katılımcıları davet edebilirsin.</p>
          <div className="hero-actions" style={{ justifyContent: "center" }}>
            <Link className="btn btn-primary" href="/login">Giriş yap</Link>
            <Link className="btn" href="/register">Kayıt ol</Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="container page-pad">
      <nav className="breadcrumb" aria-label="Konum">
        <Link href="/">ETKİNLİKLER</Link>
        <span>/</span>
        <span>YENİ ETKİNLİK</span>
      </nav>

      <div className="section-head">
        <div>
          <div className="eyebrow">02 / YENİ KAYIT</div>
          <h1 className="section-title">Etkinlik ekle</h1>
        </div>
        <p className="section-lead">
          Fotoğrafların bulunduğu Drive klasörünü bağla; yüz taraması arka planda
          çalışsın ve arşiv herkese açılsın.
        </p>
      </div>

      <div className="form-layout">
        <form className="form-panel" onSubmit={submit}>
          {error && <div className="alert alert-error">{error}</div>}

          <div className="form-grid">
            <div className="field full">
              <label className="label" htmlFor="title">Etkinlik adı *</label>
              <input
                id="title"
                className="input"
                required
                minLength={3}
                maxLength={160}
                placeholder="Örn. Yaz Festivali 2026"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="field full">
              <label className="label" htmlFor="description">Açıklama</label>
              <textarea
                id="description"
                className="input"
                maxLength={4000}
                placeholder="Etkinlik hakkında kısa bir not..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            <div className="field">
              <label className="label" htmlFor="date">Tarih</label>
              <input
                id="date"
                className="input"
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
              />
            </div>

            <div className="field">
              <label className="label" htmlFor="location">Konum</label>
              <input
                id="location"
                className="input"
                maxLength={200}
                placeholder="Şehir / mekân"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
            </div>

            <div className="field full">
              <label className="label" htmlFor="url">Drive klasör linki *</label>
              <input
                id="url"
                className="input"
                type="url"
                required
                placeholder="https://drive.google.com/drive/folders/..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <span className="meta">Klasör &quot;Bağlantıya sahip herkes&quot; olarak paylaşılmalı.</span>
            </div>

            <div className="field full">
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={includeSubfolders}
                  onChange={(e) => setIncludeSubfolders(e.target.checked)}
                />
                Alt klasörleri de tara
              </label>
            </div>
          </div>

          <button className="btn btn-primary submit-wide" type="submit" disabled={busy}>
            {busy ? "Oluşturuluyor..." : "Etkinliği oluştur →"}
          </button>

          {job && (
            <div className="job-status">
              <div className="meta">Tarama: {job.status} · {job.processed}/{job.total || "?"}</div>
              <div className="progress"><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
            </div>
          )}
        </form>

        <aside className="form-aside">
          <div className="aside-label">NASIL ÇALIŞIR</div>
          <ol className="how-list">
            <li><b>01</b><span>Klasörü bağla</span><p>Fotoğraf arşivinin Drive adresini gir.</p></li>
            <li><b>02</b><span>Taramayı başlat</span><p>Yüzler arka planda tespit edilir, arşiv indekslenir.</p></li>
            <li><b>03</b><span>Arşiv yayında</span><p>Etkinlik sayfası herkese açılır, katılımcılar fotoğrafını bulur.</p></li>
          </ol>
          <div className="aside-note">
            Yüz görüntüleri saklanmaz; yalnızca eşleştirme için geçici olarak işlenir.
          </div>
        </aside>
      </div>
    </main>
  );
}
