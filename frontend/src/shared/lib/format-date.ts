function toDate(input: string | Date | null | undefined): Date | null {
  if (input == null) return null;
  if (input instanceof Date) return input;
  // A bare YYYY-MM-DD is a calendar date, not an instant: anchor it at LOCAL
  // midnight so formatting never shifts the day. new Date("2026-07-01") is UTC
  // midnight, which a local-time formatter renders as Jun 30 west of UTC.
  const d = /^\d{4}-\d{2}-\d{2}$/.test(input) ? new Date(`${input}T00:00:00`) : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "May 12, 2026" */
export function formatDate(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(d);
}

/** "May 12, 2026, 3:42 PM" */
export function formatDateTime(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
}

/**
 * Human-relative date:
 *   < 60 s   → "just now"
 *   < 60 m   → "Xm ago"
 *   < 24 h   → "Xh ago"
 *   < 48 h   → "yesterday"
 *   < 14 d   → "Xd ago"
 *   < 8 w    → "Xw ago"
 *   else     → formatDate()
 */
export function formatRelativeDate(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";

  const deltaMs = Date.now() - d.getTime();
  const secs = Math.floor(deltaMs / 1000);
  const mins = Math.floor(secs / 60);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  const weeks = Math.floor(days / 7);

  if (secs < 60) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (hours < 48) return "yesterday";
  if (days < 14) return `${days}d ago`;
  if (weeks < 8) return `${weeks}w ago`;
  return formatDate(d);
}

/**
 * Day-granular relative date for *date-only* values (no time component), e.g.
 * a "last run on" calendar date. Unlike {@link formatRelativeDate} this has no
 * sub-day buckets and labels the current day "today" rather than "Xh ago":
 *   same day → "today"
 *   1 day    → "yesterday"
 *   < 14 d   → "Xd ago"
 *   < 60 d   → "Xw ago"
 *   else     → calendar date, omitting the year when it's the current year
 *
 * A bare `YYYY-MM-DD` string is interpreted at local midnight so the day
 * arithmetic doesn't drift across the UTC boundary.
 */
export function formatRelativeDay(input: string | Date | null | undefined): string {
  const d = toDate(input);
  if (!d) return "";

  const startOfDay = new Date(d);
  startOfDay.setHours(0, 0, 0, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const diffDays = Math.floor((today.getTime() - startOfDay.getTime()) / 86_400_000);
  if (diffDays <= 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 14) return `${diffDays}d ago`;
  if (diffDays < 60) return `${Math.floor(diffDays / 7)}w ago`;
  return startOfDay.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: today.getFullYear() === startOfDay.getFullYear() ? undefined : "numeric",
  });
}

/**
 * Day-granular due phrase for a date-only value (local calendar days):
 *   today → "due today" · +1 → "due tomorrow" · 2..13 → "due in N d" ·
 *   14..59 → "due in N w" · ≥60 → "due Sep 30" (year when not current) ·
 *   −1..−13 → "N d overdue" · −14..−59 → "N w overdue" ·
 *   −60..−729 → "N mo overdue" (30-day months) · ≤−730 → "N y overdue".
 * `now` is injectable for tests.
 */
export function formatDue(
  input: string | Date | null | undefined,
  now: Date = new Date(),
): { label: string; overdue: boolean } | null {
  const d = toDate(input);
  if (!d) return null;
  const due = new Date(d);
  due.setHours(0, 0, 0, 0);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  // round, not floor: a DST change between the two midnights is ±1 h
  const delta = Math.round((due.getTime() - today.getTime()) / 86_400_000);
  if (delta === 0) return { label: "due today", overdue: false };
  if (delta === 1) return { label: "due tomorrow", overdue: false };
  if (delta > 1 && delta < 14) return { label: `due in ${delta} d`, overdue: false };
  if (delta >= 14 && delta < 60)
    return { label: `due in ${Math.floor(delta / 7)} w`, overdue: false };
  if (delta >= 60) {
    const sameYear = due.getFullYear() === today.getFullYear();
    const text = due.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: sameYear ? undefined : "numeric",
    });
    return { label: `due ${text}`, overdue: false };
  }
  const late = -delta;
  const label =
    late < 14
      ? `${late} d overdue`
      : late < 60
        ? `${Math.floor(late / 7)} w overdue`
        : late < 730
          ? `${Math.floor(late / 30)} mo overdue`
          : `${Math.floor(late / 365)} y overdue`;
  return { label, overdue: true };
}
