/**
 * Cursor-based pagination types shared across feature modules.
 */

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  total_count: number | null;
}
