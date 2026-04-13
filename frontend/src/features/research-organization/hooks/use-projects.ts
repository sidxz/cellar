"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import type { CreateProjectInput, Project, UpdateProjectInput } from "../types";

const projectHooks = createCrudHooks<Project, CreateProjectInput, UpdateProjectInput>({
  entityName: "Project",
  baseUrl: "/api/v1/projects",
  queryKey: ["projects"],
});

export const useProjects = projectHooks.useList;
export const useProject = projectHooks.useGet;
export const useCreateProject = projectHooks.useCreate;
export const useUpdateProject = projectHooks.useUpdate;

export function useArchiveProject() {
  const action = projectHooks.useAction("archive", "Project archived");
  return { ...action, mutate: (id: string, options?: Parameters<typeof action.mutate>[1]) => action.mutate({ id }, options) };
}
