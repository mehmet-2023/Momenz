import type { SearchResponse } from "./types";

/**
 * Arama sonuçları yalnızca kullanıcının tarayıcı belleğinde tutulur.
 * Aynı yüz + aynı etkinlik ikinci kez taranırsa sunucuya hiç istek gitmez;
 * model yükleme, yüz tespiti ve matris çarpımı tekrar yapılmaz.
 * Disk'e (localStorage/sessionStorage) yazılmaz: yüz verisi sayfa kapanınca silinir.
 */
const cache = new Map<string, SearchResponse>();
const MAX_ENTRIES = 12;

export function searchCacheKey(folderKey: string, fingerprint: string): string {
  return `${folderKey}:${fingerprint}`;
}

/** Görselin baytlarından parmak izi üretir; dosya adı/kamera zamanı önemli değil. */
export async function fingerprintFile(file: File): Promise<string> {
  const bytes = await file.arrayBuffer();
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest))
      .map((part) => part.toString(16).padStart(2, "0"))
      .join("");
  }
  // Güvenli olmayan bağlamda (http) WebCrypto yok; kaba ama yeterli anahtar.
  return `${file.size}-${file.lastModified}`;
}

export function getCachedSearch(key: string): SearchResponse | null {
  const hit = cache.get(key);
  if (!hit) return null;
  // En son kullanılanı en sona taşı: LRU tahliyesinde eski sonuç gider.
  cache.delete(key);
  cache.set(key, hit);
  return hit;
}

export function setCachedSearch(key: string, value: SearchResponse): void {
  cache.set(key, value);
  while (cache.size > MAX_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
}
