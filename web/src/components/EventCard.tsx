/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import type { Event } from "@/lib/types";

export default function EventCard({ event }: { event: Event }) {
  return (
    <Link className="event-card" href={`/events/${event.slug}`}>
      {event.cover_url ? (
        <img className="event-cover" src={event.cover_url} alt="" loading="lazy" />
      ) : (
        <div className="event-cover-empty">Kapak yok</div>
      )}
      <div className="event-card-body">
        <span className="event-date-badge">
          {event.date_label || "Tarih yakında"}
        </span>
        <div className="event-card-title">{event.title}</div>
        <div className="event-card-meta">
          {event.location || "Konum belirtilmedi"}
        </div>
      </div>
      <div className="event-card-foot">
        <span>{event.image_count} fotoğraf</span>
        <span>{event.attendee_count} katılımcı</span>
      </div>
    </Link>
  );
}
