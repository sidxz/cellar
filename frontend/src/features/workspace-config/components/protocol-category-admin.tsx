"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Badge } from "@/shared/components/ui/badge";
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
import { BookOpen, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { usePreviewNamingChange } from "../hooks/use-naming-changes";
import {
  useCreateProtocolCategory,
  useDeleteProtocolCategory,
  useProtocolCategories,
  useSeedDefaultProtocolCategories,
  useUpdateProtocolCategory,
} from "../hooks/use-protocol-categories";
import type { ProtocolCategory } from "../types";
import { NamingChangePreview } from "./naming-change-preview";

const SLOT_HELP: [string, string][] = [
  ["{target}", "the linked registry target(s), with their organism when not the home one"],
  ["{organism}", "the Organism facet"],
  ["{cell_line}", "the Cell line facet (a cell line or a cell type)"],
  ["{matrix}", "the Assay format facet (microsomes, plasma)"],
  ["{subject}", "the first of target, organism, cell line"],
  ["{discriminator}", "the discriminator, placed here instead of trailing in [ ]"],
];

function CategoryDialog({
  open,
  onOpenChange,
  category,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  category: ProtocolCategory | null;
}) {
  const [label, setLabel] = useState("");
  const [pattern, setPattern] = useState("");
  const create = useCreateProtocolCategory();
  const update = useUpdateProtocolCategory(category?.id ?? "");
  const preview = usePreviewNamingChange();
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setLabel(category?.label ?? "");
      setPattern(category?.name_pattern ?? "");
    }
  }, [open, category]);

  const save = async () => {
    if (!category) {
      await create.mutateAsync({ label: label.trim(), name_pattern: pattern.trim() || null });
      onOpenChange(false);
      return;
    }
    // An edit relabels the category's protocols: show them first; Apply saves.
    preview.mutate(
      {
        kind: "category",
        category_id: category.id,
        ...(label.trim() !== category.label ? { label: label.trim() } : {}),
        ...(pattern.trim() !== category.name_pattern ? { name_pattern: pattern.trim() } : {}),
      },
      { onSuccess: () => setConfirmOpen(true) },
    );
  };

  const apply = async () => {
    await update.mutateAsync({ label: label.trim(), name_pattern: pattern.trim() });
    setConfirmOpen(false);
    onOpenChange(false);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{category ? "Edit category" : "New category"}</DialogTitle>
            <DialogDescription>
              The pattern builds the name of every protocol in this category.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="category-label">Label</Label>
              <Input
                id="category-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g. Biofilm inhibition"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="category-pattern">Name pattern</Label>
              <Input
                id="category-pattern"
                value={pattern}
                onChange={(e) => setPattern(e.target.value)}
                placeholder={category ? "" : "Leave empty for the default"}
                className="font-mono"
              />
              {category && (
                <div>
                  <Button
                    type="button"
                    variant="link"
                    size="sm"
                    className="h-auto p-0"
                    onClick={() => setPattern(category.default_pattern)}
                  >
                    Reset to default
                  </Button>
                </div>
              )}
              <ul className="text-xs text-muted-foreground">
                {SLOT_HELP.map(([slot, meaning]) => (
                  <li key={slot}>
                    <code>{slot}</code> {meaning}
                  </li>
                ))}
                <li>Add ? to make a slot optional, e.g. {"{cell_line?}"}.</li>
              </ul>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={save} disabled={!label.trim() || create.isPending || update.isPending}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <NamingChangePreview
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        preview={preview.data}
        isLoading={preview.isPending}
        onApply={apply}
        isApplying={update.isPending}
      />
    </>
  );
}

/** Admin: protocol categories and the name patterns their protocols follow. */
export function ProtocolCategoryAdmin() {
  const { data: categories, isLoading } = useProtocolCategories();
  const seed = useSeedDefaultProtocolCategories();
  const remove = useDeleteProtocolCategory();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ProtocolCategory | null>(null);

  if (isLoading) return <SkeletonList />;

  return (
    <div>
      <PageHeader
        title="Protocol Categories"
        subtitle="Each category's pattern builds the names of its protocols."
      >
        <Button variant="outline" onClick={() => seed.mutate()} disabled={seed.isPending}>
          Add default categories
        </Button>
        <Button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        >
          <Plus className="mr-2 h-4 w-4" />
          Add category
        </Button>
      </PageHeader>

      {categories && categories.length > 0 ? (
        <div className="mt-6 rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Label</TableHead>
                <TableHead>Name pattern</TableHead>
                <TableHead className="w-[140px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {categories.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">{c.label}</TableCell>
                  <TableCell>
                    <code className="text-xs">{c.name_pattern}</code>
                    {c.name_pattern !== c.default_pattern && (
                      <Badge variant="outline" className="ml-2 text-xs">
                        custom
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditing(c);
                        setDialogOpen(true);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Delete ${c.label}`}
                      onClick={() => remove.mutate(c.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState
          variant="inline"
          icon={BookOpen}
          title="No categories yet"
          description="Add the default categories to start."
        />
      )}

      <CategoryDialog open={dialogOpen} onOpenChange={setDialogOpen} category={editing} />
    </div>
  );
}
