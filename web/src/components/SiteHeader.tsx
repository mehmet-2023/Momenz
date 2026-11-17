"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { auth } from "@/lib/api";
import type { User } from "@/lib/types";

export default function SiteHeader() {
  const router = useRouter();
  const [me, setMe] = useState<User | null>(null);

  useEffect(() => {
    let alive = true;
    auth.me()
      .then((user) => {
        if (alive) setMe(user);
      })
      .catch(() => {
        if (alive) setMe(null);
      });
    return () => {
      alive = false;
    };
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

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Link href="/" className="brand">MOMENZ</Link>
        <nav className="site-nav">
          <Link href="/">Etkinlikler</Link>
          {me ? (
            <>
              <Link href="/events/new" className="nav-cta">+ Etkinlik ekle</Link>
              <span className="kicker" style={{ color: "#fff" }}>{me.email}</span>
              <button type="button" onClick={logout}>Çıkış</button>
            </>
          ) : (
            <>
              <Link href="/login">Giriş yap</Link>
              <Link href="/register" className="nav-cta">Kayıt ol</Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
