"use client";

import { useState } from "react";
import type { SearchResult } from "@/lib/types";

export default function ResultCard({ result }: { result: SearchResult }) {
  const [failed, setFailed] = useState(false);
  const thumb = result.thumb_url;

  return (
    <div className="card">
      {thumb && !failed ? (
        <img
          className="result-img"
          src={thumb}
          alt={result.name || result.file_id}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="result-img" aria-hidden="true" />
      )}
      <div className="score" style={{ marginTop: 10 }}>
        %{Math.round(result.score * 100)} eşleşme
      </div>
      <div className="meta" style={{ marginTop: 4 }}>
        {result.name || result.file_id}
      </div>
      <div className="result-actions">
        {result.drive_download_url ? (
          <a
            className="btn btn-small"
            href={result.drive_download_url}
            target="_blank"
            rel="noreferrer"
            download
          >
            DRIVE'DAN İNDİR
          </a>
        ) : result.download_url ? (
          <a className="btn btn-small" href={result.download_url} download>
            İNDİR
          </a>
        ) : null}
        <a
          className="btn btn-small"
          href={result.drive_url}
          target="_blank"
          rel="noreferrer"
        >
          DRIVE'DA AÇ
        </a>
      </div>
    </div>
  );
}
