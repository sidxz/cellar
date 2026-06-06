"use client";

import { AdminDeleteButton } from "@/shared/components/admin-delete-button";
import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
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
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, Lock, Plus, Trash2, Unlock } from "lucide-react";
import { useState } from "react";
import { useDeleteVocabulary, useVocabularies } from "../hooks/use-vocabularies";
import type { Vocabulary } from "../types";
import { VocabularyDialog } from "./vocabulary-dialog";

export function VocabularyList() {
  const { data: vocabs, isLoading } = useVocabularies();
  const deleteMutation = useDeleteVocabulary();
  const isAdmin = useAuthzHasRole("admin");
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Vocabulary | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Controlled Vocabularies"
        subtitle="Manage standardized picklists for consistent data entry."
      >
        <Button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        >
          <Plus className="mr-2 h-4 w-4" />
          Add Vocabulary
        </Button>
      </PageHeader>

      {vocabs && vocabs.length > 0 ? (
        <div className="mt-6 rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Terms</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[140px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {vocabs.map((vocab) => (
                <TableRow key={vocab.id}>
                  <TableCell className="font-medium">{vocab.name}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {vocab.terms.slice(0, 5).map((term) => (
                        <Badge key={term} variant="secondary" className="text-xs">
                          {term}
                        </Badge>
                      ))}
                      {vocab.terms.length > 5 && (
                        <Badge variant="outline" className="text-xs">
                          +{vocab.terms.length - 5} more
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {vocab.is_locked ? (
                      <Lock className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <Unlock className="h-4 w-4 text-muted-foreground" />
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditing(vocab);
                          setDialogOpen(true);
                        }}
                      >
                        Edit
                      </Button>
                      {!vocab.is_locked && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteMutation.mutate(vocab.id)}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      )}
                      {isAdmin && (
                        <AdminDeleteButton
                          entityType="vocabulary"
                          entityId={vocab.id}
                          entityLabel={vocab.name}
                          onDeleted={() => qc.invalidateQueries({ queryKey: ["vocabularies"] })}
                        />
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState variant="inline" icon={BookOpen} title="No vocabularies yet." />
      )}

      <VocabularyDialog open={dialogOpen} onOpenChange={setDialogOpen} vocabulary={editing} />
    </>
  );
}
