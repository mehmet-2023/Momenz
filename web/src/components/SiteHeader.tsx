"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/AuthProvider";
import { auth, ensureCsrf } from "@/lib/api";

export default function SiteHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const { me, loading, setMe } = useAuth();

  useEffect(() => {
    void ensureCsrf();
  }, []);

  async function logout() {
    try {
      await auth.logout();
    } finally {
      setMe(null);
      router.push("/");
      router.refresh();
    }
  }

  function isActive(href: string) {
    if (href === "/") return pathname === "/" || pathname.startsWith("/events");
    return pathname === href;
  }

  return (
    <header className="masthead">
      <div className="masthead-inner">
        <Link href="/" className="wordmark" aria-label="Momenz ana sayfa">
          MOMENZ<span className="wordmark-dot">.</span>
        </Link>

        <nav className="masthead-nav" aria-label="Ana menü">
          <Link className={isActive("/") ? "active" : ""} href="/">
            Etkinlikler
          </Link>

          {loading ? (
            <span className="nav-skeleton" aria-hidden="true" />
          ) : me ? (
            <>
              <Link
                className={isActive("/events/new") ? "active" : ""}
                href="/events/new"
              >
                Etkinlik ekle
              </Link>
              <span className="nav-user" title={me.email}>
                {me.name || me.email.split("@")[0]}
              </span>
              <button type="button" onClick={logout}>
                Çıkış
              </button>
            </>
          ) : (
            <>
              <Link className={isActive("/login") ? "active" : ""} href="/login">
                Giriş yap
              </Link>
              <Link className="nav-cta" href="/register">
                Kayıt ol
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
