"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { CreateTargetInput, Target, UpdateTargetInput } from "../types";

const targetHooks = createCrudHooks<Target, CreateTargetInput, UpdateTargetInput>({
  entityName: "Target",
  baseUrl: "/api/v1/targets",
  queryKey: ["targets"],
});

export const useTargets = targetHooks.useList;
export const useTarget = targetHooks.useGet;
export const useCreateTarget = targetHooks.useCreate;
export const useUpdateTarget = targetHooks.useUpdate;
export const useDeleteTarget = targetHooks.useDelete;
