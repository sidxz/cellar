// Re-export V2 scaffold-tree types
export * from "./scaffold-tree";

// ---------------------------------------------------------------------------
// V3 — UMAP cluster map wire types
// ---------------------------------------------------------------------------

import type {
  UmapResultDto,
  UmapJobDto,
} from "@/shared/lib/api/model";

export type UmapPicker = "maxmin" | "butina";

export interface UmapPoint {
  moleculeId: string;
  x: number;
  y: number;
}

export interface ClusterAssignment {
  moleculeId: string;
  clusterId: number;
}

export interface RepresentativePick {
  moleculeId: string;
  clusterId: number;
}

export interface UmapResult {
  points: UmapPoint[];
  clusters: ClusterAssignment[];
  representatives: RepresentativePick[];
  clusterCount: number;
  picker: UmapPicker;
  pickerParams: Record<string, unknown>;
  skippedMoleculeIds: string[];
}

export interface UmapJob {
  id: string;
  status: "pending" | "running" | "ready" | "failed" | "cancelled";
  picker: UmapPicker;
  pickerParams: Record<string, unknown>;
  errorMessage?: string | null;
}

export type ColorMode = "cluster" | "activity" | "scaffold" | "none";

export function dtoToUmapResult(dto: UmapResultDto): UmapResult {
  return {
    points: dto.points.map((p) => ({ moleculeId: p.molecule_id, x: p.x, y: p.y })),
    clusters: dto.clusters.map((c) => ({
      moleculeId: c.molecule_id,
      clusterId: c.cluster_id,
    })),
    representatives: dto.representatives.map((r) => ({
      moleculeId: r.molecule_id,
      clusterId: r.cluster_id,
    })),
    clusterCount: dto.cluster_count,
    picker: dto.picker as UmapPicker,
    pickerParams: dto.picker_params,
    skippedMoleculeIds: dto.skipped_molecule_ids,
  };
}

export function dtoToUmapJob(dto: UmapJobDto): UmapJob {
  return {
    id: dto.id,
    status: dto.status as UmapJob["status"],
    picker: dto.picker as UmapPicker,
    pickerParams: dto.picker_params,
    errorMessage: dto.error_message ?? null,
  };
}
