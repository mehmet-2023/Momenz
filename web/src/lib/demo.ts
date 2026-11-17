import type { Event, EventPhoto, SearchResponse, SearchResult } from "./types";

// ============================================================
// ⚠️ GEÇİCİ TEST VERİSİ — canlıya almadan önce BU DOSYAYI SİL.
// ============================================================

export const DEMO_FOLDER_KEY = "demo-klasor";

export const DEMO_EVENT: Event = {
  id: "demo-etkinlik-1",
  slug: "test-etkinlik",
  title: "Test Etkinliği",
  description:
    "Bu bir deneme etkinliğidir. Etkinlik sırasında çekilen binlerce fotoğraf arasından yüzünü nasıl bulabileceğini görmek için yüzünü yükle, eşleşen kareleri gör.",
  location: "Test Mekânı",
  event_date: "2026-11-20",
  date_label: "20 Kas 2026",
  folder_key: DEMO_FOLDER_KEY,
  cover_url: "/demo/kapak.svg",
  image_count: 4,
  face_count: 7,
  attendee_count: 12,
  is_attending: false,
  is_owner: false,
  created_at: "2026-11-17T00:00:00Z",
};

export const DEMO_PHOTOS: EventPhoto[] = [
  { file_id: "demo-1", name: "foto_001.jpg", thumb_url: "/demo/foto-1.svg", width: 1200, height: 800 },
  { file_id: "demo-2", name: "foto_014.jpg", thumb_url: "/demo/foto-2.svg", width: 1200, height: 800 },
  { file_id: "demo-3", name: "foto_042.jpg", thumb_url: "/demo/foto-3.svg", width: 1200, height: 800 },
  { file_id: "demo-4", name: "foto_098.jpg", thumb_url: "/demo/foto-4.svg", width: 1200, height: 800 },
];

export const DEMO_SEARCH_RESULTS: SearchResult[] = [
  {
    file_id: "demo-1",
    name: "foto_001.jpg",
    path: "/demo/foto-1.svg",
    score: 0.94,
    width: 1200,
    height: 800,
    thumb_url: "/demo/foto-1.svg",
    download_url: "/demo/foto-1.svg",
    drive_url: "#",
  },
  {
    file_id: "demo-3",
    name: "foto_042.jpg",
    path: "/demo/foto-3.svg",
    score: 0.88,
    width: 1200,
    height: 800,
    thumb_url: "/demo/foto-3.svg",
    download_url: "/demo/foto-3.svg",
    drive_url: "#",
  },
  {
    file_id: "demo-2",
    name: "foto_014.jpg",
    path: "/demo/foto-2.svg",
    score: 0.81,
    width: 1200,
    height: 800,
    thumb_url: "/demo/foto-2.svg",
    download_url: "/demo/foto-2.svg",
    drive_url: "#",
  },
];

export const DEMO_SEARCH_RESPONSE: SearchResponse = {
  folder_key: DEMO_FOLDER_KEY,
  count: DEMO_SEARCH_RESULTS.length,
  results: DEMO_SEARCH_RESULTS,
  took_ms: 412,
};
