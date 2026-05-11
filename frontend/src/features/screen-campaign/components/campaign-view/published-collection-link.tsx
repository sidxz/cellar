"use client";

/**
 * PublishedCollectionLink — Task 9.1
 *
 * Renders a link to the published Collection for this campaign, or a
 * placeholder text when the id is not yet available.
 */

import Link from "next/link";
import { LibrarySquare } from "lucide-react";

interface PublishedCollectionLinkProps {
  id?: string | null;
}

export function PublishedCollectionLink({ id }: PublishedCollectionLinkProps) {
  if (!id) {
    return (
      <p className="text-sm text-muted-foreground italic">
        No collection published yet.
      </p>
    );
  }

  return (
    <Link
      href={`/collections/${id}`}
      className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
    >
      <LibrarySquare className="h-4 w-4 shrink-0" />
      View published collection
    </Link>
  );
}
