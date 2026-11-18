"use client";

/* eslint-disable @next/next/no-img-element */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
} from "react";
import ResultCard from "@/components/ResultCard";
import { ApiError, downloadMatchesZip, searchFace } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";

type Mode = "upload" | "camera";
type Quality = 480 | 720;

export default function FaceSearch({ folderKey }: { folderKey: string }) {
  const [mode, setMode] = useState<Mode>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [quality, setQuality] = useState<Quality>(720);
  const [zipBusy, setZipBusy] = useState(false);
  const [zipError, setZipError] = useState("");
  const [error, setError] = useState("");
  const [cameraError, setCameraError] = useState("");
  const [cameraOn, setCameraOn] = useState(false);
  const [busy, setBusy] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const previewRef = useRef("");

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOn(false);
  }, []);

  const startCamera = useCallback(async () => {
    setCameraError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Bu tarayıcı kamerayı desteklemiyor. Fotoğraf yükleyebilirsin.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
    } catch {
      setCameraError(
        "Kameraya erişilemedi. İzin verdiğinden emin ol ya da fotoğraf yükle.",
      );
    }
  }, []);

  useEffect(() => {
    if (mode === "camera") void startCamera();
    else stopCamera();
  }, [mode, startCamera, stopCamera]);

  useEffect(() => {
    return () => {
      stopCamera();
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
  }, [stopCamera]);

  // Eşleşen fotoğraflar tek seferde değil, kısa aralıklarla sırayla görünür.
  useEffect(() => {
    const total = results?.results.length ?? 0;
    setVisibleCount(0);
    if (!total) return;
    const step = Math.max(1, Math.ceil(total / 24));
    let shown = 0;
    const timer = window.setInterval(() => {
      shown = Math.min(total, shown + step);
      setVisibleCount(shown);
      if (shown >= total) window.clearInterval(timer);
    }, 170);
    return () => window.clearInterval(timer);
  }, [results]);

  function pick(next: File | null) {
    if (!next) return;
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const url = URL.createObjectURL(next);
    previewRef.current = url;
    setPreview(url);
    setFile(next);
    setResults(null);
    setError("");
    setZipError("");
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    pick(event.target.files?.[0] || null);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    pick(event.dataTransfer.files?.[0] || null);
  }

  function capture() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        pick(new File([blob], `kamera-${Date.now()}.jpg`, { type: "image/jpeg" }));
        setMode("upload");
      },
      "image/jpeg",
      0.9,
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !folderKey) return;
    setBusy(true);
    setError("");
    setResults(null);
    setZipError("");
    try {
      setResults(await searchFace(folderKey, file));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Arama başarısız.");
    } finally {
      setBusy(false);
    }
  }

  async function downloadAll() {
    if (!results?.results.length) return;
    setZipBusy(true);
    setZipError("");
    try {
      await downloadMatchesZip(
        folderKey,
        results.results.map((item) => item.file_id),
        quality,
      );
    } catch (cause) {
      setZipError(cause instanceof ApiError ? cause.message : "ZIP indirilemedi.");
    } finally {
      setZipBusy(false);
    }
  }

  const allResults = results?.results ?? [];

  return (
    <section className="face-stage" id="kendini-bul">
      <div className="face-stage-head">
        <div className="eyebrow">01 / YÜZ TANIMA</div>
        <h2 className="face-stage-title">Kendini bul.</h2>
        <p className="face-stage-lead">
          Yüzünü yükle ya da kameralı çek. Bu etkinliğin kareleri arasında
          sana ait olanları bulalım.
        </p>
      </div>

      <div className="face-stage-grid">
        <div className="face-input-panel">
          <div className="face-tabs" role="tablist" aria-label="Görsel kaynağı">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "upload"}
              className={mode === "upload" ? "active" : ""}
              onClick={() => setMode("upload")}
            >
              ⬆ FOTOĞRAF YÜKLE
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "camera"}
              className={mode === "camera" ? "active" : ""}
              onClick={() => setMode("camera")}
            >
              ◉ ANLIK KAMERA
            </button>
          </div>

          {mode === "upload" ? (
            <div
              className={`face-drop${file ? " has-file" : ""}`}
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleDrop}
            >
              {preview ? (
                <>
                  <img src={preview} alt="Seçilen yüz" className="face-preview" />
                  <div className="face-file-name">{file?.name}</div>
                  <button
                    className="face-change"
                    type="button"
                    onClick={() => inputRef.current?.click()}
                  >
                    Başka fotoğraf seç
                  </button>
                </>
              ) : (
                <button
                  className="face-drop-inner"
                  type="button"
                  onClick={() => inputRef.current?.click()}
                >
                  <span className="face-drop-mark">⌖</span>
                  <b>Fotoğrafını buraya bırak</b>
                  <span>ya da seçmek için tıkla</span>
                </button>
              )}
              <input
                ref={inputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={handleChange}
              />
            </div>
          ) : (
            <div className="face-camera">
              <video ref={videoRef} muted playsInline autoPlay />
              <div className="face-camera-frame" aria-hidden="true">
                <span className="cam-corner tl" />
                <span className="cam-corner tr" />
                <span className="cam-corner bl" />
                <span className="cam-corner br" />
                <span className="cam-line" />
              </div>
              {!cameraOn && !cameraError && (
                <div className="face-camera-hint">Kamera açılıyor...</div>
              )}
              {cameraError && <div className="face-camera-hint">{cameraError}</div>}
              <button
                className="cam-shutter"
                type="button"
                onClick={capture}
                disabled={!cameraOn}
                aria-label="Fotoğraf çek"
              >
                <span />
              </button>
              <canvas ref={canvasRef} hidden />
            </div>
          )}

          <form onSubmit={submit} className="face-actions">
            <button
              className="btn btn-primary face-submit"
              type="submit"
              disabled={!file || busy}
            >
              {busy ? "ARANIYOR..." : "FOTOĞRAFLARIMI BUL →"}
            </button>
            <div className="face-privacy-note">
              Yüz verin saklanmaz. Yalnızca bu etkinlikle karşılaştırılır.
            </div>
          </form>
        </div>
      </div>

      {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}

      {results === null ? null : allResults.length === 0 ? (
        <div className="face-empty">Bu etkinlikte yüzünle eşleşen fotoğraf bulunamadı.</div>
      ) : (
        <div className="face-results">
          <div className="results-toolbar">
            <p className="caption">
              <strong>{results.count} fotoğraf bulundu.</strong> En yüksek benzerlik: %
              {Math.round(allResults[0].score * 100)} · {results.took_ms} ms
            </p>
            <div className="results-download">
              <label className="quality-select">
                <span>KALİTE</span>
                <select
                  value={quality}
                  onChange={(event) => setQuality(Number(event.target.value) as Quality)}
                  aria-label="İndirme kalitesi"
                >
                  <option value={720}>720p</option>
                  <option value={480}>480p</option>
                </select>
              </label>
              <button
                className="btn btn-small"
                type="button"
                onClick={downloadAll}
                disabled={zipBusy}
              >
                {zipBusy ? "HAZIRLANIYOR..." : `TOPLU İNDİR (${allResults.length})`}
              </button>
            </div>
          </div>
          {zipError && <div className="alert alert-error">{zipError}</div>}
          <div className="grid">
            {allResults.slice(0, visibleCount).map((item) => (
              <div className="result-reveal" key={item.file_id}>
                <ResultCard result={item} />
              </div>
            ))}
          </div>
          {visibleCount < allResults.length && (
            <div className="results-loading">
              FOTOĞRAFLAR YÜKLENİYOR · {visibleCount}/{allResults.length}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
