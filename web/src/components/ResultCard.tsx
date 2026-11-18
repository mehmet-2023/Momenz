/* eslint-disable @next/next/no-img-element */
import type { SearchResult } from "@/lib/types";

export default function ResultCard({ result }: { result: SearchResult }) {
  return (
    <div className="card">
      <img
        className="result-img"
        src={result.thumb_url}
        alt={result.name || result.file_id}
      />
      <div className="score" style={{ marginTop: 10 }}>
        %{Math.round(result.score * 100)} eşleşme
      </div>
      <div className="meta" style={{ marginTop: 4 }}>
        {result.name || result.file_id}
      </div>
      <div className="result-actions">
        {result.download_url && (
          <a className="btn btn-small" href={result.download_url} download>
            İndir
          </a>
        )}
        <a className="btn btn-small" href={result.drive_url} target="_blank" rel="noreferrer">
          Drive
        </a>
      </div>
    </div>
  );
}
