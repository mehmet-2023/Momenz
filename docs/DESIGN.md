# Momenz Tasarım Sistemi (AI-slop yok)

Mevcut Streamlit prototipindeki görsel dil **korunur**. Bu bir bilinçli seçim:
jenerik AI estetiği (mor/mavi gradient, glow, glassmorphism, yuvarlak kartlar,
"hero blob") kullanılmaz. Referans: `app.py` içindeki `<style>` bloğu.

## Token'lar

| Token | Değer | Kullanım |
|---|---|---|
| `--ink` | `#0a0a0a` | Zemin (hero), metin, kenarlık |
| `--paper` | `#ffffff` | Sayfa zemini, kart |
| `--soft` | `#f3f3f0` | Vurgulu yüzey, dropzone |
| `--muted` | `#686868` | Açıklama metni |
| `--line` | `#0a0a0a` | 1px kenarlık |

## Tipografi

- **Display / etiket / buton:** `Space Mono`, `letter-spacing: -.045em`,
  uppercase etiketlerde `.2em`, `font-size: .68rem`.
- **Gövde:** `Inter`, `line-height: 1.45–1.55`.
- Hero başlık: `clamp(2.4rem, 6vw, 4.8rem)`, `line-height: .95`,
  `letter-spacing: -.07em`.

## Kurallar

1. **Köşe yok.** `border-radius: 0` her yerde.
2. **Gölge yok.** `box-shadow: none`; sadece 1px katı kenarlık.
3. **Renk yok.** Siyah, beyaz, soft gri. Tek vurgu "invert" (siyah zemin →
   beyaz metin, hover'da tersine döner).
4. **Izgara.** Masaüstünde 3 kolonlu sonuç grid'i, mobilde 1. Container
   `max-width: 1080px`.
5. **Adım numaraları.** `01 / 02 / 03` kutucukları, 1px border, mono font.
6. **Boşluk.** Bölümler arası 48px, hero altı 56px.
7. **Animasyon.** Sadece hover'da 150ms `background/color` geçişi. Yoksa yok.

## Next.js tarafında

Bu token'lar `web/src/app/globals.css` içinde CSS custom property olarak
tanımlanır; Tailwind kullanılıyorsa `tailwind.config.ts` içinde `theme.extend`
ile eşlenir. Fontlar `next/font/google` ile self-host edilir (harici CSS
@import olmaz — hem hız hem CSP).

Yasaklı: `bg-gradient-*`, `backdrop-blur`, `shadow-*`, `rounded-*`,
`purple-*`, `blue-*`, `animate-pulse` dekoratif kullanımı.
