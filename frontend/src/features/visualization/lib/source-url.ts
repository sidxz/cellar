import type { DatasetRequest } from "@/shared/lib/api/model";
import type { DatasetSource, Level } from "../types";
import { LEVEL_ORDER } from "./levels";

type Params = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || undefined;

/** `/assays/visualize?run=<id>` or `?protocol=<id>[&runs=<id,id>]` (no `runs` = every run),
 * plus `&level=<level>` for any level but wells. With ``viewId``, the saved view's own path
 * `/assays/visualize/<viewId>?…`, the source and level overriding its saved ones (so the
 * level is always named: left out, the view would reopen at its saved level). */
export function visualizeHref(
  source: DatasetSource,
  level: Level = "wells",
  viewId?: string,
): string {
  const q = new URLSearchParams(
    source.kind === "run"
      ? { run: source.runId }
      : {
          protocol: source.protocolId,
          ...(source.runIds ? { runs: source.runIds.join(",") } : {}),
        },
  );
  if (level !== "wells" || viewId) q.set("level", level);
  return `/assays/visualize${viewId ? `/${viewId}` : ""}?${q}`;
}

/** The dataset endpoint's request for ``source`` at ``level`` (also a saved view's dataset). */
export function toDatasetRequest(source: DatasetSource, level: Level): DatasetRequest {
  return {
    level,
    source:
      source.kind === "run"
        ? { kind: "run", run_id: source.runId }
        : { kind: "protocol", protocol_id: source.protocolId, run_ids: source.runIds ?? null },
  };
}

/** The inverse of `toDatasetRequest`. */
export function fromDatasetRequest(req: DatasetRequest): { source: DatasetSource; level: Level } {
  const s = req.source;
  const source: DatasetSource =
    s.kind === "run"
      ? { kind: "run", runId: s.run_id }
      : s.run_ids?.length
        ? { kind: "protocol", protocolId: s.protocol_id, runIds: s.run_ids }
        : { kind: "protocol", protocolId: s.protocol_id };
  return { source, level: req.level };
}

/** The URL's level; wells when it names none or one that does not exist. */
export function levelFromParams(params: Params): Level {
  const level = one(params.level);
  return LEVEL_ORDER.find((l) => l === level) ?? "wells";
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
