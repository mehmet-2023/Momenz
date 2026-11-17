export type User = {
  id: string;
  email: string;
  name: string | null;
  role: string;
  is_active: boolean;
  email_verified: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
};

export type Folder = {
  key: string;
  title: string;
  folder_id: string | null;
  url: string | null;
  image_count: number;
  face_count: number;
  hidden: boolean;
  date_label: string | null;
  created_at?: string | null;
};

export type Job = {
  id: string;
  folder_key: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed" | "canceled";
  progress: number;
  processed: number;
  total: number;
  error?: string | null;
  result?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type SearchResult = {
  file_id: string;
  name: string;
  path: string | null;
  score: number;
  width: number;
  height: number;
  thumb_url: string;
  download_url: string;
  drive_url: string;
};

export type SearchResponse = {
  folder_key: string;
  count: number;
  results: SearchResult[];
  took_ms: number;
};

export type Event = {
  id: string;
  slug: string;
  title: string;
  description: string;
  location: string;
  event_date: string | null;
  date_label: string | null;
  folder_key: string;
  cover_url: string | null;
  image_count: number;
  face_count: number;
  attendee_count: number;
  is_attending: boolean;
  is_owner: boolean;
  created_at?: string | null;
};

export type EventPhoto = {
  file_id: string;
  name: string;
  thumb_url: string;
  width: number;
  height: number;
};

export type EventList = { items: Event[]; total: number };
export type EventPhotoList = { items: EventPhoto[]; total: number };

export type RegisterPayload = {
  email: string;
  password: string;
  name?: string;
};
