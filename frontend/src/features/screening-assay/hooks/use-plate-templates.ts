"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type {
  CreatePlateTemplateInput,
  PlateTemplate,
  UpdatePlateTemplateInput,
} from "../types";

const ptHooks = createCrudHooks<PlateTemplate, CreatePlateTemplateInput, UpdatePlateTemplateInput>({
  entityName: "Plate template",
  baseUrl: "/api/v1/plate-templates",
  queryKey: ["plate-templates"],
});

export const usePlateTemplates = ptHooks.useList;
export const usePlateTemplate = ptHooks.useGet;
export const useCreatePlateTemplate = ptHooks.useCreate;
export const useUpdatePlateTemplate = ptHooks.useUpdate;
export const useDeletePlateTemplate = ptHooks.useDelete;
