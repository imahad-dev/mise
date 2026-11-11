import { cache } from "react";
import { cookies } from "next/headers";

const API_URL = process.env.API_URL ?? "http://api:8000";
const GUEST_COOKIE = "mise_guest";

export interface ServerVenue {
  slug: string;
  name: string;
  /** The visit (guest session) id; only on session-resolved pages. */
  visitId?: string;
}

/** The venue of this browser's guest session, or null when there is none or it has expired. */
export const venueFromSession = cache(async (): Promise<ServerVenue | null> => {
  const cookie = (await cookies()).get(GUEST_COOKIE);
  if (!cookie) return null;
  try {
    const res = await fetch(`${API_URL}/api/guest/session`, {
      headers: { cookie: `${GUEST_COOKIE}=${cookie.value}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const s = await res.json();
    return s?.venue?.slug ? { slug: s.venue.slug, name: s.venue.name, visitId: s.id } : null;
  } catch {
    return null;
  }
});

// Tokens are token_urlsafe(12) (scripts/seed.py): base64url characters only.
const QR_TOKEN = /^[A-Za-z0-9_-]{1,128}$/;

/** The venue a table QR token belongs to, or null for a bad token. */
export const venueFromQr = cache(async (token: string): Promise<ServerVenue | null> => {
  if (!QR_TOKEN.test(token)) return null;
  try {
    const res = await fetch(`${API_URL}/api/guest/venues/${encodeURIComponent(token)}`, { cache: "no-store" });
    if (!res.ok) return null;
    const v = await res.json();
    return v?.slug ? { slug: v.slug, name: v.name } : null;
  } catch {
    return null;
  }
});
