"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type {
  DerivePlateInput,
  MoleculePlateEntry,
  RegisteredPlate,
  RegisterPlateInput,
  UpdatePlateInput,
  WellMapping,
} from "../types/plates";

const PLATES_KEY = ["plates"];

export function usePlates(params?: {
  barcode?: string;
  plate_type?: string;
  status?: string;
  format?: string;
}) {
  // Build clean params object (omit undefined values)
  const cleanParams: Record<string, string> = {};
  if (params?.barcode) cleanParams.barcode = params.barcode;
  if (params?.plate_type) cleanParams.plate_type = params.plate_type;
  if (params?.status) cleanParams.status = params.status;
  if (params?.format) cleanParams.format = params.format;

  return useQuery({
    queryKey: [...PLATES_KEY, params],
    queryFn: () =>
      customInstance<RegisteredPlate[]>({
        url: "/api/v1/plates",
        method: "GET",
        params: Object.keys(cleanParams).length > 0 ? cleanParams : undefined,
      }),
  });
}

export function usePlate(id: string | undefined) {
  return useQuery({
    queryKey: [...PLATES_KEY, id],
    queryFn: () =>
      customInstance<RegisteredPlate>({
        url: `/api/v1/plates/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useRegisterPlate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RegisterPlateInput) =>
      customInstance<RegisteredPlate>({
        url: "/api/v1/plates",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Plate registered");
    },
  });
}

export function useUpdatePlate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdatePlateInput) =>
      customInstance<RegisteredPlate>({
        url: `/api/v1/plates/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Plate updated");
    },
  });
}

export function useMapWells(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (well_map: Record<string, WellMapping>) =>
      customInstance<RegisteredPlate>({
        url: `/api/v1/plates/${id}/wells`,
        method: "PUT",
        data: { well_map },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Well mapping updated");
    },
  });
}

export function useChangeStatus(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (new_status: string) =>
      customInstance<RegisteredPlate>({
        url: `/api/v1/plates/${id}/status`,
        method: "PATCH",
        data: { new_status },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Status changed");
    },
  });
}

export function useDerivePlate(parentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: DerivePlateInput) =>
      customInstance<RegisteredPlate>({
        url: `/api/v1/plates/${parentId}/derive`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Daughter plate created");
    },
  });
}

export function useDeletePlate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `/api/v1/plates/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Plate deleted");
    },
  });
}

export function usePlateChildren(parentId: string | undefined) {
  return useQuery({
    queryKey: [...PLATES_KEY, parentId, "children"],
    queryFn: () =>
      customInstance<RegisteredPlate[]>({
        url: `/api/v1/plates/${parentId}/children`,
        method: "GET",
      }),
    enabled: !!parentId,
  });
}

const MOLECULES_KEY = ["molecules"];

export function useMoleculePlates(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...MOLECULES_KEY, moleculeId, "plates"],
    queryFn: () =>
      customInstance<MoleculePlateEntry[]>({
        url: `/api/v1/molecules/${moleculeId}/plates`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}
