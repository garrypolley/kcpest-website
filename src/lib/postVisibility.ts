/**
 * Treat `pubDate` in front matter as a **calendar day** (matches YAML `YYYY-MM-DD`).
 * A post is "public" when that day is on or before **today** in America/Chicago
 * (business timezone for KC Pest Experts).
 */
export const POST_PUBLIC_TIMEZONE = "America/Chicago";

function postScheduleDayIso(pubDate: Date): string {
  const y = pubDate.getUTCFullYear();
  const m = String(pubDate.getUTCMonth() + 1).padStart(2, "0");
  const d = String(pubDate.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function todayIsoInChicago(now: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: POST_PUBLIC_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** True when the post should appear in the blog index and get a built page. */
export function isPostPublicByPubDate(pubDate: Date, now: Date = new Date()): boolean {
  if (import.meta.env.PUBLIC_SHOW_FUTURE_POSTS === "true") {
    return true;
  }
  return postScheduleDayIso(pubDate) <= todayIsoInChicago(now);
}
