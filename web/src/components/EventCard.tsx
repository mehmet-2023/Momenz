import Link from "next/link";
import type { Event } from "@/lib/types";

type Props = {
  event: Event;
  view?: "grid" | "list";
};

export default function EventCard({ event, view = "grid" }: Props) {
  return (
    <Link className={`event-card${view === "list" ? " event-row" : ""}`} href={`/events/${event.slug}`}>
      <div className="event-media">
        {event.cover_url ? (
          <img src={event.cover_url} alt="" loading="lazy" decoding="async" />
        ) : (
          <div className="event-cover-empty">
            {event.drive_pending ? "FOTOĞRAF YAKINDA" : "KAPAK YOK"}
          </div>
        )}
        <span className="event-date-badge">
          {event.date_label || (event.drive_pending ? "YAKINDA" : "TARİH YAKINDA")}
        </span>
      </div>
      <div className="event-card-body">
        <div className="event-card-title">{event.title}</div>
        <div className="event-card-meta">
          {event.drive_pending
            ? "Fotoğraflar yakında · Hatırlatma açık"
            : event.date_label
              ? `${event.date_label} · Drive yükleme`
              : "Drive'dan yüklendi"}
        </div>
        {event.description && view === "list" && (
          <p className="event-card-desc">{event.description}</p>
        )}
      </div>
      <div className="event-card-foot">
        <span>{event.image_count} FOTOĞRAF</span>
        <span>{event.face_count} YÜZ</span>
        <span className="event-card-arrow" aria-hidden="true">→</span>
      </div>
    </Link>
  );
}
