"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  ParsedPlateMap,
  PlateSetupInput,
  PlateSetupResult,
  PlateMapResponse,
  ImportReadoutsResult,
} from "../types";

const PLATE_MAP_KEY = ["plate-map"];

export function useParsePlateMap(runId: string) {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return customInstance<ParsedPlateMap>({
        url: `/api/v1/runs/${runId}/plate-setup/parse`,
        method: "POST",
        data: formData,
      });
    },
  });
}

export function useSetUpPlate(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: PlateSetupInput) =>
      customInstance<PlateSetupResult>({
        url: `/api/v1/runs/${runId}/plate-setup`,
        method: "POST",
        data: input,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...PLATE_MAP_KEY, runId] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function usePlateMap(runId: string | undefined) {
  return useQuery({
    queryKey: [...PLATE_MAP_KEY, runId],
    queryFn: () =>
      customInstance<PlateMapResponse>({
        url: `/api/v1/runs/${runId}/plate-map`,
        method: "GET",
      }),
    enabled: !!runId,
  });
}

export function useImportReadouts(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      readoutDefinitionId,
    }: {
      file: File;
      readoutDefinitionId?: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      const params = readoutDefinitionId
        ? `?readout_definition_id=${readoutDefinitionId}`
        : "";
      return customInstance<ImportReadoutsResult>({
        url: `/api/v1/runs/${runId}/import-readouts${params}`,
        method: "POST",
        data: formData,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dose-response-curves"] });
      qc.invalidateQueries({ queryKey: ["readout-data"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}
