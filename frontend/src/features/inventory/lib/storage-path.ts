import type { StorageLocation } from "../types";

/** Names from the root down to `id`; [] when unknown. Cycle-guarded. */
export function storageChain(
  locations: StorageLocation[] | undefined,
  id: string | null | undefined,
): string[] {
  if (!locations || !id) return [];
  const byId = new Map(locations.map((l) => [l.id, l]));
  const names: string[] = [];
  const seen = new Set<string>();
  let cur = byId.get(id);
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id);
    names.unshift(cur.name);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return names;
}

/** "Room 1148 › Freezer 3" — the last `depth` levels; "" when unknown. */
export function storagePath(
  locations: StorageLocation[] | undefined,
  id: string | null | undefined,
  depth = 2,
): string {
  return storageChain(locations, id).slice(-depth).join(" › ");
}

export function storageFullPath(
  locations: StorageLocation[] | undefined,
  id: string | null | undefined,
): string {
  return storageChain(locations, id).join(" › ");
}
