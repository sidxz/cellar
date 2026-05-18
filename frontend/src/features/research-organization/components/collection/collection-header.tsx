"use client";

import { type ReactNode, useRef, useEffect } from "react";
import Link from "next/link";
import { Lock, FlaskConical, FolderOpen } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { MemberName, OrgName } from "@/shared/components/entity-name";
import { useInlineEditCollectionName } from "@/features/research-organization/hooks/use-inline-edit-collection-name";

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
  /** Optional content pinned to the right of the meta strip (e.g. selection toolbar + view toggle). */
  rightSlot?: ReactNode;
  className?: string;
}

export function CollectionHeader({
  collection,
  projectName,
  rightSlot,
  className,
}: CollectionHeaderProps) {
  const edit = useInlineEditCollectionName(collection.id, collection.name);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (edit.isEditing) inputRef.current?.focus();
  }, [edit.isEditing]);

  return (
    <header className={className}>
      {/* Single-row meta strip */}
      <div className="flex items-center gap-x-3 gap-y-1 flex-wrap">
        {/* Inline-editable name — leads the strip; reads as a heading at base size */}
        {edit.isEditing ? (
          <input
            ref={inputRef}
            type="text"
            autoComplete="off"
            aria-label="Collection name"
            className="text-sm font-medium bg-background border rounded px-2 py-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={edit.draft}
            onChange={(e) => edit.setDraft(e.target.value)}
            onBlur={edit.commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                inputRef.current?.blur(); // single commit path via onBlur
              } else if (e.key === "Escape") {
                e.preventDefault();
                edit.cancel(); // cancel resets draft; subsequent blur is a no-op (unchanged guard)
              }
            }}
          />
        ) : (
          <button
            type="button"
            className="text-sm font-medium text-foreground hover:bg-muted rounded px-1 -mx-1 disabled:opacity-60 disabled:hover:bg-transparent"
            onClick={edit.startEdit}
            disabled={edit.isPending}
            title="Click to rename"
            aria-label={`Rename collection: ${collection.name}`}
          >
            {collection.name}
          </button>
        )}

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
          </span>
          {collection.owned_by_org_id && (
            <span>
              Org: <OrgName id={collection.owned_by_org_id} />
            </span>
          )}
        </div>
        {/* Right slot: selection toolbar + view toggle, pinned to end */}
        {rightSlot && (
          <div className="ml-auto flex items-center gap-2">{rightSlot}</div>
        )}
      </div>

      {/* Description — only rendered when non-empty, always on its own line */}
      {collection.description && (
        <p className="mt-1.5 text-sm text-muted-foreground">{collection.description}</p>
      )}
    </header>
  );
}
