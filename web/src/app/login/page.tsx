"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, auth, ensureCsrf } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      await auth.login(email, password);
      router.push("/");
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Giriş yapılamadı. Tekrar dene.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <h1 className="auth-title">Giriş yap</h1>

        {error && <div className="alert alert-error">{error}</div>}

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
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "Giriş yapılıyor..." : "Giriş yap"}
        </button>

        <p className="auth-foot">
          Hesabın yok mu? <Link href="/register">Kayıt ol</Link>
        </p>
      </form>
    </main>
  );
}
