"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import ResultCard from "@/components/ResultCard";
import Step from "@/components/Step";
import {
  ApiError,
  auth,
  createFolder,
  deleteFolder,
  ensureCsrf,
  getJob,
  listFolders,
  searchFace,
} from "@/lib/api";
import type { Folder, Job, SearchResponse, User } from "@/lib/types";

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Bir hata oluştu.";
}

export default function Home() {
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<User | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [folderKey, setFolderKey] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [faceFile, setFaceFile] = useState<File | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState<"folder" | "search" | null>(null);
  const [error, setError] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    (async () => {
      try {
        await ensureCsrf();
        const user = await auth.me();
        if (!mounted.current) return;
        setMe(user);
        const items = await listFolders();
        if (!mounted.current) return;
        setFolders(items);
        if (items[0]) setFolderKey(items[0].key);
      } catch {
        // Giriş yapılmamış — landing görünümü kalır.
      } finally {
        if (mounted.current) setReady(true);
      }
    })();
    return () => {
      mounted.current = false;
    };
  }, []);

  const pollJob = useCallback(async (id: string) => {
    for (let attempt = 0; attempt < 180; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      if (!mounted.current) return;
      try {
        const current = await getJob(id);
        if (!mounted.current) return;
        setJob(current);
        if (["done", "failed", "canceled"].includes(current.status)) {
          const items = await listFolders();
          if (!mounted.current) return;
          setFolders(items);
          if (current.folder_key) setFolderKey(current.folder_key);
          return;
        }
      } catch {
        // Geçici D1 hatası — bir sonraki turda tekrar dene.
      }
    }
  }, []);

  async function handleAddFolder(event: FormEvent) {
    event.preventDefault();
    if (!newUrl.trim()) return;
    setBusy("folder");
    setError("");
    try {
      const { folder, jobId } = await createFolder(newUrl.trim());
      if (!mounted.current) return;
      setFolders((prev) => [folder, ...prev]);
      setFolderKey(folder.key);
      setNewUrl("");
      setResults(null);
      if (jobId) {
        const initial = await getJob(jobId);
        if (!mounted.current) return;
        setJob(initial);
        void pollJob(jobId);
      }
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  async function handleDeleteFolder(key: string) {
    setError("");
    try {
      await deleteFolder(key);
      if (!mounted.current) return;
      const remaining = folders.filter((item) => item.key !== key);
      setFolders(remaining);
      if (folderKey === key) setFolderKey(remaining[0]?.key || "");
      setResults(null);
    } catch (cause) {
      setError(messageOf(cause));
    }
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    if (!faceFile || !folderKey) return;
    setBusy("search");
    setError("");
    setResults(null);
    try {
      const response = await searchFace(folderKey, faceFile);
      if (mounted.current) setResults(response);
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  async function handleLogout() {
    try {
      await auth.logout();
    } finally {
      if (!mounted.current) return;
      setMe(null);
      setFolders([]);
      setFolderKey("");
      setResults(null);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFaceFile(event.target.files?.[0] || null);
    setResults(null);
  }

  const activeFolder = folders.find((item) => item.key === folderKey);
  const scanning = job && !["done", "failed", "canceled"].includes(job.status);

  return (
    <>
      <header className="hero">
        <div className="hero-inner">
          <div className="hero-top">
            <div className="brand">BY OCAL</div>
            <div className="hero-nav">
              <span className="kicker">DRIVE YÜZ TANIMA SİSTEMİ</span>
              <nav style={{ display: "flex", gap: 16 }}>
                {me ? (
                  <>
                    <span className="kicker" style={{ color: "#fff" }}>{me.email}</span>
                    <button type="button" onClick={handleLogout}>Çıkış</button>
                  </>
                ) : (
                  <>
                    <Link href="/login">Giriş yap</Link>
                    <Link href="/register">Kayıt ol</Link>
                  </>
                )}
              </nav>
            </div>
          </div>
          <h1>Fotoğrafta<br />kendini bul.</h1>
          <p>
            Klasörünü ekle ya da kayıtlı klasörlerden seç, yüzünü yükle,
            eşleşen fotoğrafları gör.
          </p>
        </div>
      </header>

      <main className="container">
        {error && <div className="alert alert-error">{error}</div>}

        <Step
          number="01"
          title="Fotoğrafların olduğu klasör"
          description="Daha önce eklediğin bir klasörü seç ya da yeni bir Drive klasör linki yapıştır."
          note="Klasör Drive'da 'Bağlantıya sahip herkes' olarak paylaşılmış olmalı."
        >
          {!ready ? (
            <p className="caption">Yükleniyor...</p>
          ) : !me ? (
            <div className="alert">
              Klasör eklemek ve arama yapmak için{" "}
              <Link href="/login">giriş yap</Link> ya da{" "}
              <Link href="/register">kayıt ol</Link>.
            </div>
          ) : (
            <>
              {folders.length > 0 && (
                <div className="folder-list">
                  {folders.map((item) => (
                    <div
                      key={item.key}
                      className={`card card-row${item.key === folderKey ? " active" : ""}`}
                    >
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => {
                          setFolderKey(item.key);
                          setResults(null);
                        }}
                      >
                        {item.key === folderKey ? "Seçili" : "Seç"}
                      </button>
                      <div style={{ flex: 1 }}>
                        <div className="card-title">{item.title}</div>
                        <div className="meta">
                          {item.image_count} fotoğraf · {item.face_count} yüz
                          {item.date_label ? ` · ${item.date_label}` : ""}
                        </div>
                      </div>
                      <div className="card-actions">
                        <button
                          type="button"
                          className="btn btn-small btn-danger"
                          onClick={() => handleDeleteFolder(item.key)}
                          disabled={busy !== null}
                        >
                          Sil
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <form onSubmit={handleAddFolder}>
                <div className="form-row">
                  <input
                    className="input"
                    type="url"
                    value={newUrl}
                    onChange={(event) => setNewUrl(event.target.value)}
                    placeholder="https://drive.google.com/drive/folders/..."
                    aria-label="Drive klasör linki"
                    disabled={busy !== null}
                  />
                  <button className="btn" type="submit" disabled={busy !== null || !newUrl.trim()}>
                    Klasör ekle
                  </button>
                </div>
              </form>

              {job && (
                <div style={{ marginTop: 16 }}>
                  <div className="meta">
                    Tarama: {job.status} · {job.processed}/{job.total || "?"} fotoğraf
                    {job.error ? ` · ${job.error}` : ""}
                  </div>
                  <div className="progress">
                    <span style={{ width: `${Math.round(job.progress * 100)}%` }} />
                  </div>
                </div>
              )}
              {activeFolder && !scanning && (
                <p className="caption">
                  Seçili klasör hazır. Sonuçlar 02&apos;de yüz yükleyince görünür.
                </p>
              )}
            </>
          )}
        </Step>

        <div className="rule" />

        <Step
          number="02"
          title="Yüzünü yükle"
          description="Net, önden çekilmiş bir fotoğraf seç veya kamerayla anlık çek."
          note="Yüklenen fotoğraf saklanmaz; yalnızca taranan fotoğraflarla karşılaştırılır."
        >
          <form onSubmit={handleSearch}>
            <div className="form-row">
              <label
                className="btn"
                style={{ display: "inline-flex", alignItems: "center", flex: "0 0 auto" }}
              >
                Fotoğraf seç
                <input
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={handleFileChange}
                  disabled={!me || !folderKey || busy !== null}
                />
              </label>
              <label
                className="btn"
                style={{ display: "inline-flex", alignItems: "center", flex: "0 0 auto" }}
              >
                Kamera ile çek
                <input
                  type="file"
                  accept="image/*"
                  capture="user"
                  hidden
                  onChange={handleFileChange}
                  disabled={!me || !folderKey || busy !== null}
                />
              </label>
              <span className="meta" style={{ flex: 1, alignSelf: "center" }}>
                {faceFile ? faceFile.name : "Dosya seçilmedi"}
              </span>
              <button
                className="btn btn-primary"
                type="submit"
                style={{ width: "auto", padding: ".65rem .9rem", fontSize: ".68rem" }}
                disabled={!me || !folderKey || !faceFile || busy !== null}
              >
                {busy === "search" ? "Aranıyor..." : "Yüzü ara"}
              </button>
            </div>
          </form>
        </Step>

        <div className="rule" />

        <Step number="03" title="Eşleşen fotoğraflar" description="Sonuçlar benzerlik sırasına göre gelir.">
          {results === null ? (
            <p className="caption">
              {!me
                ? "Devam etmek için giriş yap."
                : !folderKey
                  ? "Önce 01'de bir klasör seç."
                  : !faceFile
                    ? "Yüz fotoğrafını yükleyince sonuçlar burada görünür."
                    : "Sonuçlar hazırlanıyor."}
            </p>
          ) : results.count === 0 ? (
            <>
              <p className="caption">Eşleşme bulunamadı.</p>
              <div className="no-image">Sonuç yok</div>
            </>
          ) : (
            <>
              <p className="caption">
                <strong>{results.count} fotoğraf bulundu.</strong> En yüksek benzerlik: %
                {Math.round(results.results[0].score * 100)} · {results.took_ms} ms
              </p>
              <div className="grid">
                {results.results.map((item) => (
                  <ResultCard key={item.file_id} result={item} />
                ))}
              </div>
            </>
          )}
        </Step>

        <footer className="footer">
          <span>BY OCAL · MOMENZ</span>
          <span>Üçüncü taraf yüz tanıma servisi kullanılmaz · Sonuçları gözle doğrula</span>
        </footer>
      </main>
    </>
  );
}
