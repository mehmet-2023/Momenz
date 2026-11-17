import Link from "next/link";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div>
          <div className="site-footer-brand">MOMENZ.</div>
          <p>Etkinliklerde yüz tanıma. Binlerce fotoğrafın arasında kendini bul.</p>
        </div>
        <div className="site-footer-links">
          <Link href="/">Etkinlikler</Link>
          <Link href="/events/new">Etkinlik ekle</Link>
          <Link href="/login">Giriş yap</Link>
        </div>
        <div className="site-footer-note">
          <span>© {new Date().getFullYear()} MOMENZ · BY OCAL</span>
          <span>Etkinliğe özel eşleştirme. Sonuçları gözle doğrula.</span>
        </div>
      </div>
    </footer>
  );
}
