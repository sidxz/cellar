"use client";

import Link from "next/link";
import { cn } from "@/shared/lib/utils";

type EntityType =
  | "compound"
  | "batch"
  | "sample"
  | "protocol"
  | "run"
  | "organization";

const ENTITY_PATHS: Record<EntityType, string> = {
  compound: "/compounds",
  batch: "/inventory/batches",
  sample: "/inventory/samples",
  protocol: "/assays/protocols",
  run: "/assays/runs",
  organization: "/admin/organizations",
};

interface EntityLinkProps {
  type: EntityType;
  id: string;
  label: string;
  className?: string;
}

export function EntityLink({ type, id, label, className }: EntityLinkProps) {
  return (
    <Link
      href={`${ENTITY_PATHS[type]}/${id}`}
      className={cn(
        "font-mono text-sm text-primary underline-offset-4 hover:underline",
        className
      )}
      onClick={(e) => e.stopPropagation()}
    >
      {label}
    </Link>
  );
}
