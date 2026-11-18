"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import LoadingScreen from "@/components/LoadingScreen";
import { ApiError, createEvent, ensureCsrf, getJob } from "@/lib/api";
import type { Event, Job } from "@/lib/types";

const TERMINAL = ["done", "failed", "canceled"];

function mmss(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function phaseFor(job: Job | null) {
  if (!job) return { no: "00", title: "Hazırlanıyor", line: "Kapılar açılıyor..." };
  if (job.status === "done")
    return { no: "05", title: "Tamamlandı", line: "Hepsi burada. Fotoğrafların hazır!" };
  if (job.status === "failed")
    return { no: "!!", title: "Bir şeyler ters gitti", line: "Tekrar deneyeceğiz, sorun değil." };
  if (job.status === "canceled")
    return { no: "--", title: "İptal edildi", line: "Tamam, vazgeçtik." };
  const p = job.progress * 100;
  if (p < 3) return { no: "01", title: "Klasör açılıyor", line: "Drive kapısı aralanıyor..." };
  if (p < 25) return { no: "02", title: "Fotoğraflar sayılıyor", line: "Bir, iki, üç... binlerce." };
  if (p < 60) return { no: "03", title: "Yüzler aranıyor", line: "Herkes kadraja girdi mi?" };
  if (p < 90) return { no: "04", title: "Kareler eşleştiriliyor", line: "Sabır, bu kısım biraz uzun sürüyor." };
  return { no: "04", title: "Son rötuşlar", line: "Neredeyse bitti, paniğe gerek yok." };
}

export default function NewEventPage() {
  const router = useRouter();
  const { me, loading: authLoading } = useAuth();

  const [url, setUrl] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [event, setEvent] = useState<Event | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    void ensureCsrf();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Indexleme sırasında job durumunu yokla; bitince dur.
  // 4 sn'den başlayıp 8 sn'ye çıkan aralık: Vercel hit kotasını korur.
  useEffect(() => {
    if (!job || TERMINAL.includes(job.status)) return;
    let delay = 4000;
    let timer = 0;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        const current = await getJob(job.id);
        if (cancelled) return;
        setJob(current);
        delay = 4000;
        if (TERMINAL.includes(current.status)) return;
      } catch {
        delay = Math.min(8000, delay * 2);
      }
      timer = window.setTimeout(() => void tick(), delay);
    };
    timer = window.setTimeout(() => void tick(), delay);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [job?.id, job?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit(e: FormEvent) {
    e.preventDefault();
    const clean = url.trim();
    if (!clean) return;
    setBusy(true);
    setError("");
    try {
      const created = await createEvent({ url: clean });
      setEvent(created.event);
      setJob(created.jobId ? await getJob(created.jobId) : null);
      setStartedAt(Date.now());
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Etkinlik oluşturulamadı. Tekrar dene.",
      );
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setJob(null);
    setEvent(null);
    setUrl("");
    setError("");
    setStartedAt(null);
  }

  if (authLoading) {
    return (
      <main className="container page-pad">
        <LoadingScreen variant="form" label="OTURUM KONTROL EDİLİYOR" />
      </main>
    );
  }

  if (!me) {
    return (
      <main className="container page-pad">
        <div className="empty-state">
          <div className="empty-mark">↗</div>
          <h3>Etkinlik eklemek için giriş yap.</h3>
          <p>Drive linkini bırak, gerisini yüz tanıma sistemi halletsın.</p>
          <div className="hero-actions" style={{ justifyContent: "center" }}>
            <Link className="btn btn-primary" href="/login">Giriş yap</Link>
            <Link className="btn" href="/register">Kayıt ol</Link>
          </div>
        </div>
      </main>
    );
  }

  const phase = phaseFor(job);
  const pct = job ? Math.min(100, Math.round(job.progress * 100)) : 0;
  const elapsed = startedAt ? Math.floor((now - startedAt) / 1000) : 0;
  const done = job?.status === "done";
  const failed = job?.status === "failed" || job?.status === "canceled";
  const time = mmss(elapsed);

  const logs = job
    ? [
        `[00:00] İŞ ${job.id.slice(0, 8).toUpperCase()} KUYUĞA ALINDI`,
        `[00:01] DRIVE KLASÖRÜ BAĞLANDI`,
        job.total > 0 ? `[00:02] ${job.total} FOTOĞRAF TESPİT EDİLDİ` : `[00:02] KLASÖR TARANIYOR`,
        job.processed > 0 ? `[${time}] ${job.processed} FOTOĞRAF İŞLENDİ` : null,
        done ? `[${time}] İNDEKS GÜNCELLENDİ · TAMAMLANDI` : null,
        failed ? `[${time}] İŞ DURDURULDU` : null,
      ].filter(Boolean) as string[]
    : [];

  return (
    <main className="container page-pad new-event-page">
      <nav className="breadcrumb" aria-label="Gezinme">
        <Link href="/">ETKİNLİKLER</Link>
        <span>/</span>
        <span>YENİ ETKİNLİK</span>
      </nav>

      {!job ? (
        <>
          <div className="section-head">
            <div>
              <div className="eyebrow">02 / YENİ ETKİNLİK</div>
              <h1 className="section-title">Etkinliği bağla.</h1>
            </div>
            <p className="section-lead">
              Tek bir Drive linki. Başlık, fotoğraf sayısı ve yükleme tarihi
              klasörden otomatik okunur; sen sadece yüz tanımanın başlamasını beklersin.
            </p>
          </div>

          <div className="link-panel">
            <div className="link-panel-head">
              <span className="step-no">01</span>
              <div>
                <div className="step-title">Drive klasörünün linki</div>
                <div className="step-desc">
                  Klasör &quot;Bağlantıya sahip herkes&quot; olarak paylaşılmalı.
                  Başka bir şey girmene gerek yok.
                </div>
              </div>
            </div>

            <form onSubmit={submit}>
              {error && <div className="alert alert-error">{error}</div>}
              <div className="link-field">
                <span className="link-prefix" aria-hidden="true">⌖</span>
                <input
                  className="link-input"
                  type="url"
                  required
                  autoFocus
                  placeholder="https://drive.google.com/drive/folders/..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  aria-label="Drive klasör linki"
                />
                <button className="btn btn-primary link-submit" type="submit" disabled={busy || !url.trim()}>
                  {busy ? "Bağlanıyor..." : "Taramayı başlat →"}
                </button>
              </div>
            </form>

            <div className="auto-grid">
              <div><b>BAŞLIK</b><span>Drive klasör adı</span></div>
              <div><b>FOTOĞRAF</b><span>Klasörden sayılır</span></div>
              <div><b>YÜKLEME TARİHİ</b><span>Drive metadata</span></div>
              <div><b>THUMBNAIL</b><span>Otomatik üretilir</span></div>
            </div>
          </div>

          <div className="aside-note new-note">
            İpucu: Etkinlikten sonra klasöre yeni fotoğraf eklersen tekrar taramayı
            başlatman yeterli; yüzler güncellenir.
          </div>
        </>
      ) : (
        <div className="index-console">
          <div className="console-head">
            <div className="console-status">
              <span className={`console-dot${done ? " is-done" : failed ? " is-fail" : ""}`} />
              {done ? "TAMAMLANDI" : failed ? "DURDURULDU" : "INDEXLEME AKTİF"}
            </div>
            <div className="console-timer">GEÇEN {time}</div>
          </div>

          <div className="console-body">
            <div className="scan-stage" aria-hidden="true">
              <div className="scan-grid" />
              <div className="scan-frame scan-frame-a" />
              <div className="scan-frame scan-frame-b" />
              <div className="scan-crosshair" />
              <div className="scan-beam" />
              <div className="scan-counter">
                <b>{String(job.processed).padStart(4, "0")}</b>
                <span>FOTOĞRAF</span>
              </div>
            </div>

            <div className="console-info">
              <div className="phase-index">{phase.no} / 05</div>
              <h2 key={phase.title} className="phase-title">{phase.title}</h2>
              <p key={phase.line} className="phase-line">{phase.line}</p>

              <div className="index-meter">
                <div className="meter-head">
                  <span>İLERLEME</span>
                  <b>{pct}%</b>
                </div>
                <div className="meter-track">
                  <span style={{ width: `${pct}%` }} />
                </div>
                <div className="meter-foot">
                  <span>{job.processed} / {job.total || "?"} fotoğraf</span>
                  <span>{job.status.toUpperCase()}</span>
                </div>
              </div>

              <div className="console-quip">
                {done
                  ? "Kahve soğumadan bitti."
                  : "Bu biraz sürebilir. Kahve koy, hatta ikincisini de koyabilirsin."}
              </div>

              {done && event && (
                <div className="console-actions">
                  <Link className="btn btn-primary" href={`/events/${event.slug}`}>
                    Etkinliği aç →
                  </Link>
                  <button className="btn" type="button" onClick={reset}>
                    Yeni etkinlik
                  </button>
                </div>
              )}

              {failed && (
                <div className="console-actions">
                  <button className="btn btn-primary" type="button" onClick={reset}>
                    Tekrar dene
                  </button>
                  {job.error && <span className="meta">{job.error}</span>}
                </div>
              )}
            </div>
          </div>

          <div className="console-log">
            <div className="log-label">CANLI KAYIT</div>
            <div className="log-lines">
              {logs.map((line, i) => (
                <div key={`${line}-${i}`} className="log-line">{line}</div>
              ))}
              {!done && !failed && <div className="log-cursor">_</div>}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
