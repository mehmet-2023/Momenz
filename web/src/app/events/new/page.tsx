"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import SiteHeader from "@/components/SiteHeader";
import { ApiError, auth, createEvent, ensureCsrf, getJob } from "@/lib/api";
import type { Job, User } from "@/lib/types";

const CATEGORIES = ["diger", "muzik", "spor", "sergi", "kampus", "topluluk"];

export default function NewEventPage() {
  const router = useRouter();
  const [me, setMe] = useState<User | null | undefined>(undefined);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("diger");
  const [location, setLocation] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [url, setUrl] = useState("");
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureCsrf();
    auth.me().then(setMe).catch(() => setMe(null));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { event: created, jobId } = await createEvent({
        title,
        description,
        category,
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
              // geçici hata
            }
          }
        })();
      }
      router.push(`/events/${created.slug}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Etkinlik oluşturulamadı.");
    } finally {
      setBusy(false);
    }
  }

  if (me === undefined) {
    return <><SiteHeader /><main className="container"><p className="caption">Yükleniyor...</p></main></>;
  }

  if (!me) {
    return (
      <>
        <SiteHeader />
        <main className="container">
          <div className="alert">
            Etkinlik eklemek için <Link href="/login">giriş yap</Link> ya da{" "}
            <Link href="/register">kayıt ol</Link>.
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <SiteHeader />
      <main className="container">
        <section className="page-intro">
          <div className="eyebrow">YENİ ETKİNLİK</div>
          <h1 className="page-title">Etkinlik ekle</h1>
          <p className="page-lead">
            Fotoğrafların olduğu Drive klasörünü bağla; yüz taraması arka planda
            çalışsın. Klasör &quot;Bağlantıya sahip herkes&quot; olarak paylaşılmış olmalı.
          </p>
        </section>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={submit}>
          <div className="form-grid">
            <div className="field full">
              <label className="label" htmlFor="title">Etkinlik adı</label>
              <input id="title" className="input" required minLength={3} maxLength={160}
                value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="field full">
              <label className="label" htmlFor="description">Açıklama</label>
              <textarea id="description" className="input" maxLength={4000}
                value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="field">
              <label className="label" htmlFor="date">Tarih</label>
              <input id="date" className="input" type="date"
                value={eventDate} onChange={(e) => setEventDate(e.target.value)} />
            </div>
            <div className="field">
              <label className="label" htmlFor="location">Konum</label>
              <input id="location" className="input" maxLength={200}
                value={location} onChange={(e) => setLocation(e.target.value)} />
            </div>
            <div className="field">
              <label className="label" htmlFor="category">Kategori</label>
              <select id="category" className="input"
                value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div className="field">
              <label className="label" htmlFor="url">Drive klasör linki</label>
              <input id="url" className="input" type="url" required
                placeholder="https://drive.google.com/drive/folders/..."
                value={url} onChange={(e) => setUrl(e.target.value)} />
            </div>
            <div className="field full">
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: ".85rem" }}>
                <input type="checkbox" checked={includeSubfolders}
                  onChange={(e) => setIncludeSubfolders(e.target.checked)} />
                Alt klasörleri de tara
              </label>
            </div>
          </div>

          <button className="btn btn-primary" type="submit" disabled={busy} style={{ maxWidth: 320, marginTop: 12 }}>
            {busy ? "Oluşturuluyor..." : "Etkinliği oluştur"}
          </button>
        </form>

        {job && (
          <div style={{ marginTop: 22, maxWidth: 480 }}>
            <div className="meta">Tarama: {job.status} · {job.processed}/{job.total || "?"}</div>
            <div className="progress"><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
          </div>
        )}

        <footer className="footer">
          <span>BY OCAL · MOMENZ</span>
          <span>Etkinlik sayfasına yönlendirildikten sonra tarama devam eder.</span>
        </footer>
      </main>
    </>
  );
}
