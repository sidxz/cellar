import { useMemo } from "react";
import {
  type FacetGroup,
  type FacetSelections,
  type GroupBy,
  type ProtocolGroup,
  type ShortLabels,
  buildFacetModel,
  filterProtocols,
  groupProtocols,
} from "../lib/protocol-facets";
import type { Protocol } from "../types";

/** The faceting seam: pure logic memoized. A future server-side facet endpoint
 *  replaces this hook's internals without touching any consuming component. */
export function useProtocolFacets(
  protocols: Protocol[],
  selections: FacetSelections,
  groupBy: GroupBy,
  shortLabels?: ShortLabels,
): { facetModel: FacetGroup[]; filtered: Protocol[]; groups: ProtocolGroup[] } {
  return useMemo(() => {
    const facetModel = buildFacetModel(protocols, selections, shortLabels);
    const filtered = filterProtocols(protocols, selections);
    const groups = groupProtocols(filtered, groupBy);
    return { facetModel, filtered, groups };
  }, [protocols, selections, groupBy, shortLabels]);
}
