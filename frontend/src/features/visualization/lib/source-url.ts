import type { DatasetSource, Level } from "../types";
import { LEVEL_ORDER } from "./levels";

type Params = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || undefined;

/** `/assays/visualize?run=<id>` or `?protocol=<id>[&runs=<id,id>]` (no `runs` = every run),
 * plus `&level=<level>` for any level but wells. */
export function visualizeHref(source: DatasetSource, level: Level = "wells"): string {
  const q = new URLSearchParams(
    source.kind === "run"
      ? { run: source.runId }
      : {
          protocol: source.protocolId,
          ...(source.runIds ? { runs: source.runIds.join(",") } : {}),
        },
  );
  if (level !== "wells") q.set("level", level);
  return `/assays/visualize?${q}`;
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
