"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";

/** Comma-separated names of the chosen projects, for wizard summaries. */
export function ProjectNames({ ids }: { ids: string[] }) {
  const { data: projects } = useProjects();
  const byId = new Map((projects ?? []).map((p) => [p.id, p.name]));
  return <>{ids.map((id) => byId.get(id) ?? "…").join(", ")}</>;
}
