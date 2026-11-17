"use client";

import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import ResultCard from "@/components/ResultCard";
import { ApiError, searchFace } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";

export default function FaceSearch({ folderKey }: { folderKey: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] || null);
    setResults(null);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !folderKey) return;
    setBusy(true);
    setError("");
    setResults(null);
    try {
      setResults(await searchFace(folderKey, file));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Arama başarısız.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="step-head">
        <div className="step-no">02</div>
        <div>
          <div className="step-title">Bu etkinlikte fotoğrafını bul</div>
          <div className="step-desc">Yüzünü yükle, eşleşen fotoğrafları gör.</div>
          <div className="step-note">
            Fotoğraf saklanmaz; yalnızca bu etkinliğin fotoğraflarıyla karşılaştırılır.
          </div>
        </div>
      </div>

      <form onSubmit={submit}>
        <div className="form-row">
          <button
            type="button"
            className="btn"
            onClick={() => inputRef.current?.click()}
          >
            Fotoğraf seç
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            capture="user"
            hidden
            onChange={handleChange}
          />
          <span className="meta" style={{ flex: 1, alignSelf: "center" }}>
            {file ? file.name : "Dosya seçilmedi"}
          </span>
          <button className="btn btn-primary" type="submit" style={{ width: "auto", fontSize: ".68rem", padding: ".65rem .9rem" }} disabled={!file || busy}>
            {busy ? "Aranıyor..." : "Yüzü ara"}
          </button>
        </div>
      </form>

      {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}

      {results === null ? null : results.count === 0 ? (
        <p className="caption" style={{ marginTop: 16 }}>Eşleşme bulunamadı.</p>
      ) : (
        <div style={{ marginTop: 18 }}>
          <p className="caption">
            <strong>{results.count} fotoğraf bulundu.</strong> En yüksek benzerlik: %
            {Math.round(results.results[0].score * 100)} · {results.took_ms} ms
          </p>
          <div className="grid">
            {results.results.map((item) => (
              <ResultCard key={item.file_id} result={item} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
