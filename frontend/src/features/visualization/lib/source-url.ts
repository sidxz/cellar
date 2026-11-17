import type { ComparedProtocolBody, DatasetRequest } from "@/shared/lib/api/model";
import type { ComparedProtocol, DatasetSource, Level } from "../types";
import { LEVEL_ORDER } from "./levels";

type Params = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || undefined;
const all = (v: string | string[] | undefined) => (v === undefined ? [] : [v].flat());

/** A protocol id with its run ids when some are named (none named = every run). */
const withRuns = (protocolId: string, runIds: string[] | null | undefined): ComparedProtocol =>
  runIds?.length ? { protocolId, runIds } : { protocolId };
const toBody = (c: ComparedProtocol): ComparedProtocolBody => ({
  protocol_id: c.protocolId,
  run_ids: c.runIds ?? null,
});

/** `/assays/visualize?run=<id>` or `?protocol=<id>[&runs=<id,id>]` (no `runs` = every run),
 * then one `&compare=<id>[:<run id>,<run id>]` per compared protocol, plus `&level=<level>`
 * for any level but wells. With ``viewId``, the saved view's own path
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
  if (source.kind === "protocol") {
    for (const c of source.compare ?? []) {
      q.append(
        "compare",
        c.runIds?.length ? `${c.protocolId}:${c.runIds.join(",")}` : c.protocolId,
      );
    }
  }
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
        : {
            kind: "protocol",
            protocol_id: source.protocolId,
            run_ids: source.runIds ?? null,
            ...(source.compare?.length ? { compare: source.compare.map(toBody) } : {}),
          },
  };
}

/** The inverse of `toDatasetRequest`. */
export function fromDatasetRequest(req: DatasetRequest): { source: DatasetSource; level: Level } {
  const s = req.source;
  if (s.kind === "run") return { source: { kind: "run", runId: s.run_id }, level: req.level };
  const compare = (s.compare ?? []).map((c) => withRuns(c.protocol_id, c.run_ids));
  return { source: protocolSource(s.protocol_id, s.run_ids, compare), level: req.level };
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
  const compare = all(params.compare).flatMap((entry) => {
    const [id, runs = ""] = entry.split(":");
    return id ? [withRuns(id, runs.split(",").filter(Boolean))] : [];
  });
  return protocolSource(protocolId, one(params.runs)?.split(",").filter(Boolean), compare);
}

/** A protocol source with only the fields that say something (no empty run or compare list). */
function protocolSource(
  protocolId: string,
  runIds: string[] | null | undefined,
  compare: ComparedProtocol[],
): DatasetSource {
  return {
    kind: "protocol",
    ...withRuns(protocolId, runIds),
    ...(compare.length ? { compare } : {}),
  };
}
