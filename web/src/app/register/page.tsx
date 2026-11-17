"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import { ApiError, auth, ensureCsrf } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const { setMe } = useAuth();
  const [name, setName] = useState("");
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
      await auth.register({ email, password, name: name || undefined });
      // Doğrulama yok: kayıt anında oturum açılır, doğrudan etkinliklere dön.
      const result = await auth.login(email, password);
      setMe(result.user);
      router.push("/");
      router.refresh();
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
    <main className="auth-page">
      <div className="auth-shell">
        <aside className="auth-aside">
          <h2>Kendini bulmaya<br />başla.</h2>
          <p>
            Etkinliklerde çekilen binlerce fotoğrafın arasında yüzünü bul.
            Etkinliğini ekle, katılımcılara katıl; kaydolduktan sonra hemen
            kullanmaya başla.
          </p>
        </aside>

        <div className="auth-panel">
          <div className="auth-card">
            <div className="eyebrow">02 / YENİ HESAP</div>
            <h1 className="auth-title">Kayıt ol</h1>

            {error && <div className="alert alert-error">{error}</div>}

            <form onSubmit={submit}>
              <div className="field">
                <label className="label" htmlFor="name">Ad <span className="optional">(opsiyonel)</span></label>
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

              <button className="btn btn-primary submit-wide" type="submit" disabled={busy}>
                {busy ? "Oluşturuluyor..." : "Hesabı oluştur →"}
              </button>
            </form>

            <p className="auth-foot">
              Zaten hesabın var mı? <Link href="/login">Giriş yap</Link>
            </p>
            <Link className="back-link" href="/">← Etkinliklere dön</Link>
          </div>
        </div>
      </div>
    </main>
  );
}
