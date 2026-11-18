import type { SearchResponse } from "./types";

/**
 * Yüz indeksi + arama sonuçları tarayıcıda IndexedDB'ye süresiz yazılır.
 *
 * - Aynı fotoğraf (bayt parmak izi aynı) -> 0 istek, 0 D1 okuması.
 * - Benzer yüz (kosinüs >= 0.78) -> yalnızca /search/embed (D1'siz), sonuç
 *   önbellekten gösterilir, 0 D1 okuması.
 * - Yeni yüz -> /search/embed + /search, sonra vektör ve sonuçlar saklanır.
 *
 * Klasör (etkinlik) anahtarı her kaydın içinde tutulur ve benzerlik araması
 * yalnızca o klasörün kayıtları arasında yapılır: etkinlikler birbirine
 * karışmaz. D1 her zaman source of truth'dur; önbellek yalnızca istemcidedir.
 */

const DB_NAME = "momenz-face-cache";
const STORE = "faces";
const DB_VERSION = 1;
export const SIMILARITY_THRESHOLD = 0.78;

export type CachedFace = {
  key: string;
  folderKey: string;
  fingerprint: string;
  embedding: Float32Array;
  results: SearchResponse;
  createdAt: number;
};

export type SimilarHit = {
  results: SearchResponse;
  similarity: number;
  fingerprint: string;
};

let dbPromise: Promise<IDBDatabase | null> | null = null;
const memory = new Map<string, CachedFace>();

function openDb(): Promise<IDBDatabase | null> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve) => {
    if (typeof indexedDB === "undefined") {
      resolve(null);
      return;
    }
    try {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: "key" });
          store.createIndex("folderKey", "folderKey", { unique: false });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
      req.onblocked = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return dbPromise;
}

export function searchCacheKey(folderKey: string, fingerprint: string): string {
  return `${folderKey}::${fingerprint}`;
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

function cosine(a: Float32Array, b: ArrayLike<number>): number {
  const n = Math.min(a.length, b.length);
  if (!n) return 0;
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < n; i += 1) {
    const x = a[i];
    const y = b[i];
    dot += x * y;
    normA += x * x;
    normB += y * y;
  }
  if (normA <= 1e-12 || normB <= 1e-12) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

function toFloat32(values: number[] | Float32Array | ArrayLike<number>): Float32Array {
  if (values instanceof Float32Array) return values;
  return Float32Array.from(values as ArrayLike<number>);
}

/** Exact hit: aynı yüz + aynı etkinlik. Sunucuya hiç istek gitmez. */
export async function getCachedSearch(
  folderKey: string,
  fingerprint: string,
): Promise<SearchResponse | null> {
  const key = searchCacheKey(folderKey, fingerprint);
  const db = await openDb();
  if (!db) return memory.get(key)?.results ?? null;
  return new Promise((resolve) => {
    const req = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
    req.onsuccess = () => resolve((req.result as CachedFace | undefined)?.results ?? null);
    req.onerror = () => resolve(memory.get(key)?.results ?? null);
  });
}

/**
 * Aynı etkinlik içinde en benzer önbellek kaydını bulur.
 * threshold varsayılan 0.78 (~%78); 0.70-0.80 aralığı istenen davranış.
 */
export async function findSimilarFace(
  folderKey: string,
  embedding: number[],
  threshold = SIMILARITY_THRESHOLD,
): Promise<SimilarHit | null> {
  const probe = toFloat32(embedding);
  const db = await openDb();
  let entries: CachedFace[];

  if (!db) {
    entries = Array.from(memory.values()).filter((item) => item.folderKey === folderKey);
  } else {
    entries = await new Promise<CachedFace[]>((resolve) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).index("folderKey").getAll(folderKey);
      req.onsuccess = () => resolve((req.result as CachedFace[]) ?? []);
      req.onerror = () => resolve([]);
    });
    if (!entries.length) {
      entries = Array.from(memory.values()).filter((item) => item.folderKey === folderKey);
    }
  }

  let best: SimilarHit | null = null;
  for (const entry of entries) {
    const similarity = cosine(probe, entry.embedding);
    if (similarity >= threshold && (!best || similarity > best.similarity)) {
      best = {
        results: entry.results,
        similarity,
        fingerprint: entry.fingerprint,
      };
    }
  }
  return best;
}

/** Vektörü ve sonuçları süresiz kaydeder (aynı yüz tekrar gelirse üzerine yazar). */
export async function setCachedSearch(
  folderKey: string,
  fingerprint: string,
  embedding: number[] | Float32Array,
  results: SearchResponse,
): Promise<void> {
  if (!embedding.length) return;
  const entry: CachedFace = {
    key: searchCacheKey(folderKey, fingerprint),
    folderKey,
    fingerprint,
    embedding: toFloat32(embedding),
    results,
    createdAt: Date.now(),
  };
  memory.set(entry.key, entry);

  const db = await openDb();
  if (!db) return;
  await new Promise<void>((resolve) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(entry);
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve();
    tx.onabort = () => resolve();
  });
}
