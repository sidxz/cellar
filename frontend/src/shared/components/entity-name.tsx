"use client";

import { useMolecule } from "@/features/chemical-registration/hooks/use-molecules";
import { useSynthesisRoute } from "@/features/chemical-registration/hooks/use-synthesis-routes";
import { useBatch } from "@/features/inventory/hooks/use-batches";
import { useSample } from "@/features/inventory/hooks/use-samples";
import { useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";

const LOADING = <span className="text-muted-foreground">...</span>;

/**
 * Renders a molecule's registration number and name from its ID.
 */
export function MoleculeName({ id }: { id: string }) {
  const { data, isLoading } = useMolecule(id);
  if (isLoading) return LOADING;
  if (!data) return <span className="text-muted-foreground">Unknown</span>;
  return <span>{data.registration_number ?? data.name ?? "Unknown compound"}</span>;
}

/**
 * Renders an organization's name from its ID.
 */
export function OrgName({ id }: { id: string }) {
  const { data: orgs, isLoading } = useOrganizations();
  if (isLoading) return LOADING;
  const org = orgs?.find((o) => o.id === id);
  return <span>{org?.name ?? "Unknown org"}</span>;
}

/**
 * Renders a workspace member's name from their user ID.
 */
export function MemberName({ id }: { id: string }) {
  const { data: members, isLoading } = useWorkspaceMembers();
  if (isLoading) return LOADING;
  const m = members?.find((u) => u.user_id === id);
  return <span>{m?.name ?? m?.email ?? "Unknown user"}</span>;
}

/**
 * Renders a batch number from its ID.
 */
export function BatchName({ id }: { id: string }) {
  const { data, isLoading } = useBatch(id);
  if (isLoading) return LOADING;
  if (!data) return <span className="text-muted-foreground">Unknown batch</span>;
  return <span>{data.batch_number}</span>;
}

/**
 * Renders a sample barcode from its ID.
 */
export function SampleName({ id }: { id: string }) {
  const { data, isLoading } = useSample(id);
  if (isLoading) return LOADING;
  if (!data) return <span className="text-muted-foreground">Unknown sample</span>;
  return <span>{data.barcode}</span>;
}

/**
 * Renders a protocol name from its ID.
 */
export function ProtocolName({ id }: { id: string }) {
  const { data, isLoading } = useProtocol(id);
  if (isLoading) return LOADING;
  if (!data) return <span className="text-muted-foreground">Unknown protocol</span>;
  return <span>{data.name}</span>;
}

/**
 * Renders a synthesis route name from its ID.
 */
export function RouteName({ id }: { id: string }) {
  const { data, isLoading } = useSynthesisRoute(id);
  if (isLoading) return LOADING;
  if (!data) return <span className="text-muted-foreground">Unknown route</span>;
  return <span>{data.name}</span>;
}
