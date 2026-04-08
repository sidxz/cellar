"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type {
  CreatePlateTemplateInput,
  PlateTemplate,
  UpdatePlateTemplateInput,
} from "../types";

const PLATE_TEMPLATES_KEY = ["plate-templates"];

export function usePlateTemplates() {
  return useQuery({
    queryKey: PLATE_TEMPLATES_KEY,
    queryFn: () =>
      customInstance<PlateTemplate[]>({
        url: "/api/v1/plate-templates",
        method: "GET",
      }),
  });
}

export function usePlateTemplate(id: string | undefined) {
  return useQuery({
    queryKey: [...PLATE_TEMPLATES_KEY, id],
    queryFn: () =>
      customInstance<PlateTemplate>({
        url: `/api/v1/plate-templates/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreatePlateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreatePlateTemplateInput) =>
      customInstance<PlateTemplate>({
        url: "/api/v1/plate-templates",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATE_TEMPLATES_KEY });
      showSuccess("Plate template created");
    },
  });
}

export function useUpdatePlateTemplate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdatePlateTemplateInput) =>
      customInstance<PlateTemplate>({
        url: `/api/v1/plate-templates/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATE_TEMPLATES_KEY });
      showSuccess("Plate template updated");
    },
  });
}

export function useDeletePlateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      customInstance<void>({
        url: `/api/v1/plate-templates/${id}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATE_TEMPLATES_KEY });
      showSuccess("Plate template deleted");
    },
  });
}
