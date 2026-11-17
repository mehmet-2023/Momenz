"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { ApiError, auth, ensureCsrf } from "@/lib/api";

function PasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ensureCsrf();
  }, []);

  async function requestReset(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await auth.forgotPassword(email);
      setSent(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "İşlem başarısız.");
    } finally {
      setBusy(false);
    }
  }

  async function reset(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Şifreler eşleşmiyor.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await auth.resetPassword(token!, password);
      router.push("/login?reset=1");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Şifre güncellenemedi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-shell">
        <aside className="auth-aside">
          <div className="eyebrow" style={{ color: "#9a9a9a" }}>MOMENZ / HESAP</div>
          <h2>Şifreni<br />yenile.</h2>
          <p>
            E-postana gönderilen bağlantıyla şifreni sıfırlayabilirsin.
            Bağlantı kısa süre geçerlidir ve yalnızca bir kez kullanılabilir.
          </p>
          <div className="auth-aside-foot">● MAIL YALNIZCA BU AKİŞ İÇİN</div>
        </aside>

        <div className="auth-panel">
          <div className="auth-card">
            <div className="eyebrow">{token ? "01 / YENİ ŞİFRE" : "01 / ŞİFREMİ UNUTTUM"}</div>
            <h1 className="auth-title">{token ? "Yeni şifre belirle" : "Şifreni mi unuttun?"}</h1>

            {error && <div className="alert alert-error">{error}</div>}

            {token ? (
              <form onSubmit={reset}>
                <div className="field">
                  <label className="label" htmlFor="password">Yeni şifre</label>
                  <input
                    id="password"
                    className="input"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </div>
                <div className="field">
                  <label className="label" htmlFor="confirm">Şifreyi doğrula</label>
                  <input
                    id="confirm"
                    className="input"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                  />
                </div>
                <button className="btn btn-primary submit-wide" type="submit" disabled={busy}>
                  {busy ? "Güncelleniyor..." : "Şifreyi güncelle →"}
                </button>
              </form>
            ) : sent ? (
              <div className="alert">
                Bu e-posta kayıtlıysa şifre sıfırlama bağlantısı gönderildi.
                Gelen kutunu kontrol et.
              </div>
            ) : (
              <form onSubmit={requestReset}>
                <div className="field">
                  <label className="label" htmlFor="email">E-posta</label>
                  <input
                    id="email"
                    className="input"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </div>
                <button className="btn btn-primary submit-wide" type="submit" disabled={busy}>
                  {busy ? "Gönderiliyor..." : "Sıfırlama bağlantısı gönder →"}
                </button>
              </form>
            )}

            <p className="auth-foot">
              <Link href="/login">← Giriş sayfasına dön</Link>
            </p>
            <Link className="back-link" href="/">Etkinliklere dön</Link>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function PasswordPage() {
  return (
    <Suspense
      fallback={
        <main className="auth-page">
          <div className="auth-shell">
            <div className="auth-panel">
              <p className="caption">Yükleniyor...</p>
            </div>
          </div>
        </main>
      }
    >
      <PasswordContent />
    </Suspense>
  );
}
