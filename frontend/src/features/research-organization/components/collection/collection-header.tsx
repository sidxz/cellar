"use client";

import { MemberName } from "@/shared/components/entity-name";
import { OwnerOrgLine } from "@/shared/components/owner-org-line";
import { Badge } from "@/shared/components/ui/badge";
import { useOrgName } from "@/shared/hooks/use-orgs";
import { FlaskConical, FolderOpen, Lock } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { COLLECTION_TYPE_LABELS, type CollectionType } from "../../types";
import { CollectionTypeIcon } from "./collection-type-icon";

export interface CollectionHeaderData {
  id: string;
  name: string;
  description?: string | null;
  project_id?: string | null;
  owner_org_id?: string | null;
  created_by: string;
  created_by_org_id?: string | null;
  visibility: "private" | "shared";
  molecule_count: number;
  is_frozen?: boolean;
  type?: CollectionType;
  derived_from_campaign_id?: string | null;
}

export interface CollectionHeaderProps {
  collection: CollectionHeaderData;
  projectName?: string;
  /** Optional content pinned to the right of the meta strip (e.g. selection toolbar + view toggle). */
  rightSlot?: ReactNode;
  /** An admin or the creator may hand the collection to another org. */
  canChangeOwner?: boolean;
  onChangeOwner?: (orgId: string) => Promise<unknown>;
  className?: string;
}

export function CollectionHeader({
  collection,
  projectName,
  rightSlot,
  className,
  canChangeOwner = false,
  onChangeOwner,
}: CollectionHeaderProps) {
  const orgName = useOrgName();
  return (
    <header className={className}>
      {/* Single-row meta strip */}
      <div className="flex items-center gap-x-3 gap-y-1 flex-wrap">
        {/* Left: badges + meta links + created-by */}
        <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-xs text-muted-foreground">
          <Badge variant="secondary" className="text-xs">
            {collection.molecule_count} molecule{collection.molecule_count === 1 ? "" : "s"}
          </Badge>
          <Badge
            variant={collection.visibility === "shared" ? "outline" : "secondary"}
            className="text-xs"
          >
            {collection.visibility}
          </Badge>
          {collection.type && (
            <Badge variant="outline" className="gap-1 text-xs">
              <CollectionTypeIcon type={collection.type} />
              {COLLECTION_TYPE_LABELS[collection.type]}
            </Badge>
          )}
          {collection.is_frozen && (
            <Badge variant="outline" className="text-xs">
              <Lock className="mr-1 h-3 w-3" />
              Frozen
            </Badge>
          )}
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
            {collection.created_by_org_id && <> · {orgName(collection.created_by_org_id)}</>}
          </span>
          <OwnerOrgLine
            ownerOrgId={collection.owner_org_id}
            canChange={canChangeOwner}
            onSave={onChangeOwner ?? (async () => undefined)}
          />
        </div>
        {/* Right slot: selection toolbar + view toggle, pinned to end */}
        {rightSlot && <div className="ml-auto flex items-center gap-2">{rightSlot}</div>}
      </div>

      {/* Description — only rendered when non-empty, always on its own line */}
      {collection.description && (
        <p className="mt-1.5 text-sm text-muted-foreground">{collection.description}</p>
      )}
    </header>
  );
}
