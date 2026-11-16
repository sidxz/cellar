import type { DatasetSource } from "../types";

type Params = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || undefined;

/** `/assays/visualize?run=<id>` or `?protocol=<id>[&runs=<id,id>]` (no `runs` = every run). */
export function visualizeHref(source: DatasetSource): string {
  const q = new URLSearchParams(
    source.kind === "run"
      ? { run: source.runId }
      : {
          protocol: source.protocolId,
          ...(source.runIds ? { runs: source.runIds.join(",") } : {}),
        },
  );
  return `/assays/visualize?${q}`;
}

/** The inverse of `visualizeHref`; null when the URL names no source. */
export function sourceFromParams(params: Params): DatasetSource | null {
  const run = one(params.run);
  if (run) return { kind: "run", runId: run };
  const protocolId = one(params.protocol);
  if (!protocolId) return null;
  const runIds = one(params.runs)?.split(",").filter(Boolean);
  return runIds?.length
    ? { kind: "protocol", protocolId, runIds }
    : { kind: "protocol", protocolId };
}
