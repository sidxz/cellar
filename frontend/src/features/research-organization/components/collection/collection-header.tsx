"use client";

import Link from "next/link";
import { Lock, FlaskConical, FolderOpen } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { MemberName, OrgName } from "@/shared/components/entity-name";

export interface CollectionHeaderData {
  id: string;
  name: string;
  description?: string | null;
  project_id?: string | null;
  owned_by_org_id?: string | null;
  created_by: string;
  visibility: "private" | "shared";
  molecule_count: number;
  is_frozen?: boolean;
  derived_from_campaign_id?: string | null;
}

export interface CollectionHeaderProps {
  collection: CollectionHeaderData;
  projectName?: string;
  className?: string;
}

export function CollectionHeader({
  collection,
  projectName,
  className,
}: CollectionHeaderProps) {
  return (
    <header className={className}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{collection.name}</h1>
        <Badge variant="secondary" className="text-xs">
          {collection.molecule_count} molecule{collection.molecule_count === 1 ? "" : "s"}
        </Badge>
        <Badge variant={collection.visibility === "shared" ? "outline" : "secondary"} className="text-xs">
          {collection.visibility}
        </Badge>
        {collection.is_frozen && (
          <Badge variant="outline" className="text-xs">
            <Lock className="mr-1 h-3 w-3" />
            Frozen
          </Badge>
        )}
      </div>

      {collection.description && (
        <p className="mt-1.5 text-sm text-muted-foreground">{collection.description}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {collection.project_id && projectName && (
          <Link
            href={`/projects/${collection.project_id}`}
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <FolderOpen className="h-3 w-3" />
            {projectName}
          </Link>
        )}
        {collection.derived_from_campaign_id && (
          <Link
            href={`/campaigns/${collection.derived_from_campaign_id}`}
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            <FlaskConical className="h-3 w-3" />
            from campaign
          </Link>
        )}
        <span>
          Created by <MemberName id={collection.created_by} />
        </span>
        {collection.owned_by_org_id && (
          <span>
            Org: <OrgName id={collection.owned_by_org_id} />
          </span>
        )}
      </div>
    </header>
  );
}
