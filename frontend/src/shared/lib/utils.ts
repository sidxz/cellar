import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Number of leading characters shown when truncating a UUID for display. */
export const SHORT_ID_LEN = 8;

/**
 * Truncate a UUID (or any opaque id) to its leading {@link SHORT_ID_LEN}
 * characters for display when no friendly label (reg number, name) exists.
 *
 * Returns the bare prefix with NO ellipsis — the majority of call sites use
 * the result as a label fallback (`name ?? shortId(id)`). Sites that want a
 * trailing `…` append it themselves.
 */
export function shortId(id: string): string {
  return id.slice(0, SHORT_ID_LEN);
}
