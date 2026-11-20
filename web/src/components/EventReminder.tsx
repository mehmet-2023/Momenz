"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  ensureCsrf,
  getMyEventReminder,
  subscribeEventReminder,
} from "@/lib/api";

type Props = {
  slug: string;
  /** Sahibine kaç kişinin beklediğini göster; ziyaretçide gizli kalır. */
  waiting?: number;
};

export default function EventReminder({ slug, waiting = 0 }: Props) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getMyEventReminder(slug)
      .then((result) => {
        if (active && result.subscribed) setDone(true);
      })
      .catch(() => {
        // IP sorgusu başarısızsa formu göster; kayıt akışı bozulmasın.
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [slug]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const clean = email.trim();
    if (!clean) return;
    setBusy(true);
    setError("");
    try {
      await ensureCsrf();
      await subscribeEventReminder(slug, clean);
      setDone(true);
      setEmail("");
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Kayıt alınamadı. Biraz sonra tekrar dene.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (checking && !done) return null;

  if (done) {
    return (
      <div className="reminder-done" role="status">
        <span className="reminder-mark" aria-hidden="true">✓</span>
        <div>
          <b>EMAILİNİ ALDIK</b>
          <p>
            Fotoğraflar yüklendiğinde bu e-posta adresine tek bir haber
            göndereceğiz.
          </p>
        </div>
      </div>
    );
  }

  return (
    <form className="reminder-form" onSubmit={submit}>
      <label className="label" htmlFor={`reminder-${slug}`}>
        E-POSTA İLE HABER VER
      </label>
      <div className="reminder-row">
        <input
          id={`reminder-${slug}`}
          className="input"
          type="email"
          required
          autoComplete="email"
          maxLength={254}
          placeholder="ornek@eposta.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-describedby={`reminder-note-${slug}`}
        />
        <button
          className="btn btn-primary reminder-submit"
          type="submit"
          disabled={busy || !email.trim()}
        >
          {busy ? "KAYDEDİLİYOR..." : "HABER VER →"}
        </button>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <p className="reminder-note" id={`reminder-note-${slug}`}>
        Tek bir e-posta gönderilir; reklam yok. Aynı adres aynı etkinliğe
        yalnızca bir kez eklenir.
        {waiting > 0 && (
          <span className="reminder-waiting"> · {waiting} kişi bekliyor</span>
        )}
      </p>
    </form>
  );
}
