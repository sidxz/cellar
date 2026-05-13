/** Bucket items by a derived key, preserving insertion order. */
export function groupBy<T, K>(items: Iterable<T>, keyFn: (item: T) => K): Map<K, T[]> {
  const out = new Map<K, T[]>();
  for (const item of items) {
    const k = keyFn(item);
    let bucket = out.get(k);
    if (!bucket) {
      bucket = [];
      out.set(k, bucket);
    }
    bucket.push(item);
  }
  return out;
}
