"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { BookOpen } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import {
  useCreateNamingLabel,
  useDeleteNamingLabel,
  useNamingTermsInUse,
  useUpdateNamingLabel,
} from "../hooks/use-naming-labels";
import type { NamingTermInUse } from "../types";

const SLOT_TITLES: Record<string, string> = {
  organism: "Organism",
  cell_line: "Cell line",
  assay_format: "Assay format",
  "target organism": "Target organism (from the registry)",
};

function ShortLabelDialog({
  term,
  onOpenChange,
}: {
  term: NamingTermInUse | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [value, setValue] = useState("");
  const create = useCreateNamingLabel();
  const update = useUpdateNamingLabel(term?.override_id ?? "");
  const remove = useDeleteNamingLabel();

  useEffect(() => {
    setValue(term?.override_short_label ?? term?.default_short_label ?? "");
  }, [term]);

  if (!term) return null;

  const save = async () => {
    if (term.override_id) {
      await update.mutateAsync({ short_label: value.trim() });
    } else {
      await create.mutateAsync({
        term_id: term.term_id,
        term_label: term.term_label,
        ontology_source: term.ontology_source,
        short_label: value.trim(),
      });
    }
    onOpenChange(false);
  };

  const reset = async () => {
    if (term.override_id) await remove.mutateAsync(term.override_id);
    onOpenChange(false);
  };

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{term.term_label}</DialogTitle>
          <DialogDescription>
            How this term reads inside protocol names. Default: {term.default_short_label}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="short-label">Short label</Label>
          <Input id="short-label" value={value} onChange={(e) => setValue(e.target.value)} />
        </div>
        <DialogFooter>
          {term.override_id && (
            <Button variant="outline" onClick={reset} disabled={remove.isPending}>
              Reset to default
            </Button>
          )}
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={!value.trim() || create.isPending || update.isPending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Admin: the short labels ontology terms render as inside protocol names. */
export function NamingLabelAdmin() {
  const { data: terms, isLoading } = useNamingTermsInUse();
  const [editing, setEditing] = useState<NamingTermInUse | null>(null);

  if (isLoading) return <SkeletonList />;

  const slots = [...new Set((terms ?? []).map((t) => t.slot))];

  return (
    <div>
      <PageHeader title="Short Labels" subtitle="How ontology terms read inside protocol names." />
      {terms && terms.length > 0 ? (
        <div className="mt-6 rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Term</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Protocols</TableHead>
                <TableHead>Short label</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {slots.map((slot) => (
                <Fragment key={slot}>
                  <TableRow>
                    <TableCell colSpan={5} className="bg-muted/40 text-xs font-semibold uppercase">
                      {SLOT_TITLES[slot] ?? slot}
                    </TableCell>
                  </TableRow>
                  {(terms ?? [])
                    .filter((t) => t.slot === slot)
                    .map((t) => (
                      <TableRow key={`${slot}-${t.term_id || t.term_label}`}>
                        <TableCell>{t.term_label}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {t.ontology_source}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {t.protocol_count}
                        </TableCell>
                        <TableCell>
                          {t.override_short_label ? (
                            <div>
                              <span className="font-semibold">{t.override_short_label}</span>
                              <p className="text-xs text-muted-foreground">
                                default {t.default_short_label}
                              </p>
                            </div>
                          ) : (
                            <span>{t.default_short_label}</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!t.term_id}
                            title={
                              t.term_id
                                ? undefined
                                : "Use this organism as a protocol's Organism facet to override it"
                            }
                            onClick={() => setEditing(t)}
                          >
                            Edit
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState
          variant="inline"
          icon={BookOpen}
          title="No terms yet"
          description="Terms appear here once protocols use an organism, cell line or assay format."
        />
      )}
      <ShortLabelDialog term={editing} onOpenChange={(open) => !open && setEditing(null)} />
    </div>
  );
}
