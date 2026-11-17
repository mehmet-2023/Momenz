"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, auth, ensureCsrf } from "@/lib/api";

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
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
      await auth.register({ email, password, name: name || undefined });
      setDone(true);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Kayıt oluşturulamadı. Tekrar dene.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <h1 className="auth-title">Kayıt ol</h1>

        {done ? (
          <div className="alert">
            Kayıt oluşturuldu. E-postana gelen doğrulama bağlantısını açtıktan
            sonra <Link href="/login">giriş yapabilirsin</Link>.
          </div>
        ) : (
          <>
            {error && <div className="alert alert-error">{error}</div>}

            <div className="field">
              <label className="label" htmlFor="name">Ad (opsiyonel)</label>
              <input
                id="name"
                className="input"
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>

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

            <div className="field">
              <label className="label" htmlFor="password">Şifre</label>
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
              <span className="meta">En az 8 karakter.</span>
            </div>

            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? "Oluşturuluyor..." : "Kayıt ol"}
            </button>
          </>
        )}

        <p className="auth-foot">
          Zaten hesabın var mı? <Link href="/login">Giriş yap</Link>
        </p>
      </form>
    </main>
  );
}
