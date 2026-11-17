import type { Metadata } from "next";
import { Inter, Space_Mono } from "next/font/google";
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

export const metadata: Metadata = {
  title: "Momenz — Etkinlikleri keşfet, fotoğrafını bul",
  description:
    "Topluluk etkinliklerini keşfet, fotoğraf arşivine göz at ve kendi fotoğrafını bul. Üçüncü taraf yüz tanıma servisi yok.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" className={`${inter.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
