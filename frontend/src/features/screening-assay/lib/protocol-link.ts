import { PROTOCOL_TYPE_LABELS, type ProtocolType } from "../types";

/** What a link to `/assays?new_protocol=1&…` asks the New protocol dialog to start with. */
export interface ProtocolLinkStart {
  category: string | null;
  protocolType: string | null;
  targetIds: string[];
  projectId: string | null;
}

const LINK_KEYS = ["new_protocol", "category", "protocol_type", "target_id", "project_id"];

export function readProtocolLink(params: URLSearchParams): ProtocolLinkStart | null {
  if (params.get("new_protocol") !== "1") return null;
  return {
    category: params.get("category"),
    protocolType: params.get("protocol_type"),
    targetIds: params.getAll("target_id"),
    projectId: params.get("project_id"),
  };
}

/** The query string with the link's own values removed (return_to and the rest kept). */
export function withoutProtocolLink(params: URLSearchParams): string {
  const rest = new URLSearchParams(params);
  for (const key of LINK_KEYS) rest.delete(key);
  const query = rest.toString();
  return query ? `?${query}` : "";
}

/** The link's values ChemCellar knows; anything else is dropped, never an error. */
export function resolveProtocolLink(
  start: ProtocolLinkStart,
  known: {
    categoryLabels: readonly string[];
    targetIds: readonly string[];
    projectIds: readonly string[];
  },
): {
  category: string | null;
  protocolType: ProtocolType | null;
  targetIds: string[];
  projectId: string | null;
} {
  const type = start.protocolType;
  return {
    category:
      start.category && known.categoryLabels.includes(start.category) ? start.category : null,
    protocolType: type && Object.hasOwn(PROTOCOL_TYPE_LABELS, type) ? (type as ProtocolType) : null,
    targetIds: [...new Set(start.targetIds)].filter((id) => known.targetIds.includes(id)),
    projectId:
      start.projectId && known.projectIds.includes(start.projectId) ? start.projectId : null,
  };
}
