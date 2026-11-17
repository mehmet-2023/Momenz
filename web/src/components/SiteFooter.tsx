import Link from "next/link";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div>
          <div className="site-footer-brand">MOMENZ.</div>
          <p>Topluluk fotoğraf arşivi. Etkinlikleri keşfet, kendi fotoğrafını bul.</p>
        </div>
        <div className="site-footer-links">
          <Link href="/">Etkinlikler</Link>
          <Link href="/events/new">Etkinlik ekle</Link>
          <Link href="/login">Giriş yap</Link>
        </div>
        <div className="site-footer-note">
          <span>© {new Date().getFullYear()} MOMENZ · BY OCAL</span>
          <span>Yüz verisi saklanmaz. Sonuçları gözle doğrula.</span>
        </div>
      </div>
    </footer>
  );
}
