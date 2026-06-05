"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";
import type { CreateProjectInput, Project, UpdateProjectInput } from "../types";

const PROJECTS_KEY = ["projects"];

const projectHooks = createCrudHooks<Project, CreateProjectInput, UpdateProjectInput>({
  entityName: "Project",
  baseUrl: "/api/v1/projects",
  queryKey: PROJECTS_KEY,
});

/**
 * Workspace projects list.
 *
 * - No options ⇒ workspace-wide list.
 * - `tags` + `tagLogic` filter projects by assigned tags (passed to the
 *   backend `tags` / `tag_logic` query params).
 */
export function useProjects(options?: { tags?: string[]; tagLogic?: "any" | "all" }) {
  const tags = options?.tags?.length ? options.tags : null;
  return useQuery({
    queryKey: [...PROJECTS_KEY, ...(tags ? [{ tags, tagLogic: options?.tagLogic ?? "any" }] : [])],
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (tags) {
        params.tags = tags;
        params.tag_logic = options?.tagLogic ?? "any";
      }
      const resp = await customInstance<Project[] | { items: Project[] }>({
        url: "/api/v1/projects",
        method: "GET",
        ...(Object.keys(params).length ? { params } : {}),
      });
      return Array.isArray(resp) ? resp : resp.items;
    },
  });
}

export const useProject = projectHooks.useGet;
export const useCreateProject = projectHooks.useCreate;
export const useUpdateProject = projectHooks.useUpdate;

export function useArchiveProject() {
  const action = projectHooks.useAction("archive", "Project archived");
  return {
    ...action,
    mutate: (id: string, options?: Parameters<typeof action.mutate>[1]) =>
      action.mutate({ id }, options),
  };
}
