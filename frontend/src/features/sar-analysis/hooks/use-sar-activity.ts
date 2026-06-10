"use client";

import { useExecuteSearch } from "@/features/research-organization/hooks/use-search";
import { toBackendProtocolColumns } from "@/features/research-organization/lib/protocol-column-id";
import {
  type AggregationMode,
  aggregationModeToWire,
} from "@/features/research-organization/lib/use-aggregation-mode";
import type { ActivityValue } from "@/features/research-organization/types";
import { useEffect, useState } from "react";
import type { SarColorSpec } from "../lib/sar-color-spec";

export function useSarActivity(args: {
  moleculeIds: string[];
  colorSpec: SarColorSpec | null;
  aggregationMode: AggregationMode;
}): {
  activityByMolecule: Record<string, ActivityValue | undefined>;
  isFetching: boolean;
} {
  const search = useExecuteSearch();
  const [activityByMolecule, setActivity] = useState<Record<string, ActivityValue | undefined>>({});
  const { mutateAsync } = search;
  const column = args.colorSpec?.column ?? null;
  const idsKey = args.moleculeIds.join(",");

  // biome-ignore lint/correctness/useExhaustiveDependencies: refetch keyed on idsKey/column/mode value-deps; mutateAsync identity is stable
  useEffect(() => {
    if (!column || args.moleculeIds.length === 0) {
      setActivity({});
      return;
    }
    let cancelled = false;
    mutateAsync({
      input: {
        query: {
          criteria: [{ type: "keyword_list", values: args.moleculeIds, ref_type: "uuid" }],
          logic: "and",
        },
        protocol_columns: toBackendProtocolColumns([column]),
        aggregation: aggregationModeToWire(args.aggregationMode),
      },
      limit: args.moleculeIds.length,
    })
      .then((res) => {
        if (cancelled) return;
        const out: Record<string, ActivityValue | undefined> = {};
        for (const [molId, cols] of Object.entries(res.activity_data ?? {})) {
          out[molId] = cols[column];
        }
        setActivity(out);
      })
      .catch(() => {
        if (!cancelled) setActivity({});
      });
    return () => {
      cancelled = true;
    };
  }, [idsKey, column, args.aggregationMode, mutateAsync]);

  return { activityByMolecule, isFetching: search.isPending };
}
