"use client";

import { useCallback, useEffect, useState } from "react";

const KEY_PREFIX = "cellar:cherrypick:";

function storageKey(collectionId?: string): string {
  return `${KEY_PREFIX}${collectionId ?? "_search"}`;
}

function readStored(key: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function writeStored(key: string, ids: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify([...ids]));
  } catch {
    // Storage unavailable / quota — basket stays in-memory only.
  }
}

export interface CherrypickBasket {
  ids: Set<string>;
  size: number;
  has: (id: string) => boolean;
  add: (id: string) => void;
  addMany: (ids: string[]) => void;
  remove: (id: string) => void;
  removeMany: (ids: string[]) => void;
  clear: () => void;
}

/**
 * A cherry-pick basket: an accumulating Set of molecule ids, persisted to
 * localStorage under `cellar:cherrypick:{collectionId}`. Survives reload +
 * navigation, scoped to this browser. SSR-safe (no window → in-memory only).
 */
export function useCherrypickBasket(collectionId?: string): CherrypickBasket {
  const key = storageKey(collectionId);
  const [ids, setIds] = useState<Set<string>>(() => new Set(readStored(key)));

  // Re-load when the collection (and therefore the key) changes.
  useEffect(() => {
    setIds(new Set(readStored(key)));
  }, [key]);

  const mutate = useCallback(
    (fn: (prev: Set<string>) => Set<string>) => {
      setIds((prev) => {
        const next = fn(prev);
        writeStored(key, next);
        return next;
      });
    },
    [key],
  );

  const add = useCallback(
    (id: string) => mutate((p) => new Set(p).add(id)),
    [mutate],
  );
  const addMany = useCallback(
    (arr: string[]) =>
      mutate((p) => {
        const next = new Set(p);
        for (const id of arr) next.add(id);
        return next;
      }),
    [mutate],
  );
  const remove = useCallback(
    (id: string) =>
      mutate((p) => {
        const next = new Set(p);
        next.delete(id);
        return next;
      }),
    [mutate],
  );
  const removeMany = useCallback(
    (arr: string[]) =>
      mutate((p) => {
        const next = new Set(p);
        for (const id of arr) next.delete(id);
        return next;
      }),
    [mutate],
  );
  const clear = useCallback(() => mutate(() => new Set()), [mutate]);
  const has = useCallback((id: string) => ids.has(id), [ids]);

  return { ids, size: ids.size, has, add, addMany, remove, removeMany, clear };
}
