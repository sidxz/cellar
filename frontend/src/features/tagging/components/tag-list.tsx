"use client";

import { PageHeader } from "@/shared/components/page-header";
import { TagChip } from "@/shared/components/tag-chip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { GitMerge, Pencil, Tag as TagIcon, Trash2 } from "lucide-react";
import { useState } from "react";
import { useDeleteTag, useTags } from "../hooks/use-tags";
import type { Tag } from "../types";
import { TagMergeDialog } from "./tag-merge-dialog";
import { TagRenameDialog } from "./tag-rename-dialog";

export function TagList() {
  const [q, setQ] = useState("");
  const { data: tags, isLoading } = useTags({ q: q || undefined, limit: 200 });
  const del = useDeleteTag();
  const isAdmin = useAuthzHasRole("admin");
  const [renaming, setRenaming] = useState<Tag | null>(null);
  const [merging, setMerging] = useState<Tag | null>(null);

  return (
    <>
      <PageHeader title="Tags" subtitle="Rename, merge, or remove workspace tags.">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search tags…"
          className="h-9 w-56"
        />
      </PageHeader>

      {isLoading ? (
        <div className="mt-6 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static skeleton list, order never changes
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : tags && tags.length > 0 ? (
        <div className="mt-6 rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tag</TableHead>
                <TableHead className="w-[220px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tags.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <TagChip tagKey={t.key} value={t.value} />
                  </TableCell>
                  <TableCell>
                    {isAdmin && (
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setRenaming(t)}>
                          <Pencil className="mr-1 h-3.5 w-3.5" /> Rename
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setMerging(t)}>
                          <GitMerge className="mr-1 h-3.5 w-3.5" /> Merge
                        </Button>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button variant="ghost" size="sm">
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Delete tag?</AlertDialogTitle>
                              <AlertDialogDescription>
                                Deletes <TagChip tagKey={t.key} value={t.value} /> and removes it
                                from every entity. This cannot be undone.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction onClick={() => del.mutate(t.id)}>
                                Delete
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
          <TagIcon className="h-10 w-10" />
          <p>No tags yet.</p>
        </div>
      )}

      <TagRenameDialog
        tag={renaming}
        open={!!renaming}
        onOpenChange={(o) => !o && setRenaming(null)}
      />
      <TagMergeDialog tag={merging} open={!!merging} onOpenChange={(o) => !o && setMerging(null)} />
    </>
  );
}
