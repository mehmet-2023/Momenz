"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ApiError, auth, ensureCsrf } from "@/lib/api";

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setMe } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const registered = searchParams.get("registered") === "1";
  const resetDone = searchParams.get("reset") === "1";

  useEffect(() => {
    void ensureCsrf();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await auth.login(email, password);
      setMe(result.user);
      router.push("/");
      router.refresh();
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
    <main className="auth-page">
      <div className="auth-shell">
        <aside className="auth-aside">
          <h2>Kendini<br />bulmaya hazır mısın?</h2>
          <p>
            Etkinliklerde çekilen fotoğraflar arasında yüzünü bul. Hesabın
            yoksa bir dakikada üye olabilirsin.
          </p>
        </aside>

        <div className="auth-panel">
          <div className="auth-card">
            <div className="eyebrow">01 / GİRİŞ</div>
            <h1 className="auth-title" data-text="Giriş yap">Giriş yap</h1>

            {registered && (
              <div className="alert">Kaydın oluşturuldu. Şimdi giriş yapabilirsin.</div>
            )}
            {resetDone && (
              <div className="alert">Şifren güncellendi. Yeni şifrenle giriş yap.</div>
            )}
            {error && <div className="alert alert-error">{error}</div>}

            <form onSubmit={submit}>
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
                <div className="label-row">
                  <label className="label" htmlFor="password">Şifre</label>
                  <Link className="forgot-link" href="/sifre-sifirla">
                    Şifremi unuttum
                  </Link>
                </div>
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

              <button className="btn btn-primary submit-wide" type="submit" disabled={busy}>
                {busy ? "Giriş yapılıyor..." : "Giriş yap →"}
              </button>
            </form>

            <p className="auth-foot">
              Hesabın yok mu? <Link href="/register">Kayıt ol</Link>
            </p>
            <Link className="back-link" href="/">← Etkinliklere dön</Link>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
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
      <LoginContent />
    </Suspense>
  );
}
