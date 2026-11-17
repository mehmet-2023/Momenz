import type { Metadata } from "next";
import { Chakra_Petch, Inter, Space_Mono } from "next/font/google";
import { AuthProvider } from "@/components/AuthProvider";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-mono",
  display: "swap",
});

const display = Chakra_Petch({
  subsets: ["latin", "latin-ext"],
  weight: ["500", "700"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Momenz — Etkinliklerde yüz tanıma, fotoğrafını bul",
  description:
    "Etkinliklerde çekilen binlerce fotoğrafın arasında yüz tanımayla kendi fotoğraflarını bul. Etkinliğini seç, yüzünü yükle, sana ait kareleri gör.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" className={`${inter.variable} ${mono.variable} ${display.variable}`}>
      <body>
        <AuthProvider>
          <SiteHeader />
          <div className="app-body">{children}</div>
          <SiteFooter />
        </AuthProvider>
      </body>
    </html>
  );
}
