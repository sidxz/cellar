export const NO_SCAFFOLD_SENTINEL = "__no_scaffold__";

export type ScaffoldTreeNode = {
  scaffold_smiles: string; // canonical SMILES OR NO_SCAFFOLD_SENTINEL
  molecule_ids: string[];
  molecule_count: number;
  subtree_molecule_count: number;
};

export type ScaffoldTreeEdge = {
  parent_smiles: string;
  child_smiles: string;
};

export type ScaffoldTreeStats = {
  node_count: number;
  elapsed_ms: number;
  cache_hit: boolean;
  truncated?: boolean;
};

export type ScaffoldTreeResult = {
  nodes: ScaffoldTreeNode[];
  edges: ScaffoldTreeEdge[];
  stats: ScaffoldTreeStats;
};

export type ScaffoldTreeJobStatus = "pending" | "running" | "ready" | "failed" | "cancelled";

export type ScaffoldTreeJob = {
  id: string;
  status: ScaffoldTreeJobStatus;
  ids_hash: string;
  requested_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  tree?: ScaffoldTreeResult | null;
};

export type StartScaffoldTreeResponse = {
  tree: ScaffoldTreeResult | null;
  job: Pick<
    ScaffoldTreeJob,
    "id" | "status" | "ids_hash" | "requested_at" | "started_at" | "completed_at" | "error_message"
  > | null;
};
