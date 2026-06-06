/**
 * Cursor-based pagination types shared across feature modules.
 */

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  total_count: number | null;
}

/**
 * Normalize a list endpoint response to a bare array.
 *
 * Endpoints migrated to cursor pagination return a `{ items }` envelope;
 * older ones still return a bare list. Accept both at runtime so list hooks
 * don't need to know which shape they get.
 */
export function unwrapList<T>(resp: T[] | { items: T[] }): T[] {
  return Array.isArray(resp) ? resp : resp.items;
}
