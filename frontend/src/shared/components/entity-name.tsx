"use client";

import { useMolecule } from "@/features/chemical-registration/hooks/use-molecules";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";

/**
 * Renders a molecule's registration number and name from its ID.
 * TanStack Query caches results, so repeated renders for the same ID are free.
 */
export function MoleculeName({ id }: { id: string }) {
  const { data, isLoading } = useMolecule(id);
  if (isLoading) return <span className="text-muted-foreground">...</span>;
  if (!data) return <span className="text-muted-foreground">Unknown</span>;
  return <span>{data.registration_number ?? data.name ?? id.slice(0, 8)}</span>;
}

/**
 * Renders an organization's name from its ID.
 * Uses the organizations list (typically small, cached) to find the name.
 */
export function OrgName({ id }: { id: string }) {
  const { data: orgs, isLoading } = useOrganizations();
  if (isLoading) return <span className="text-muted-foreground">...</span>;
  const org = orgs?.find((o) => o.id === id);
  return <span>{org?.name ?? "Unknown org"}</span>;
}
