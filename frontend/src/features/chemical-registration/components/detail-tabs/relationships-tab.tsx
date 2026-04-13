"use client";

import { useState } from "react";
import Link from "next/link";
import { Link2, Plus, Trash2, Search } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Textarea } from "@/shared/components/ui/textarea";
import {
  useRelationships,
  useCreateRelationship,
  useDeleteRelationship,
  useMolecule,
  useMoleculeSearch,
} from "../../hooks/use-molecules";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RELATIONSHIP_TYPES = [
  { value: "metabolite_of", label: "Metabolite of" },
  { value: "analog_of", label: "Analog of" },
  { value: "prodrug_of", label: "Prodrug of" },
  { value: "salt_of", label: "Salt of" },
  { value: "enantiomer_of", label: "Enantiomer of" },
  { value: "component_of", label: "Component of" },
] as const;

const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  RELATIONSHIP_TYPES.map((t) => [t.value, t.label])
);

// ---------------------------------------------------------------------------
// RelationshipsTab
// ---------------------------------------------------------------------------

interface RelationshipsTabProps {
  moleculeId: string;
}

export function RelationshipsTab({ moleculeId }: RelationshipsTabProps) {
  const { data: relationships, isLoading } = useRelationships(moleculeId);
  const deleteMutation = useDeleteRelationship(moleculeId);
  const [addOpen, setAddOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Relationships</CardTitle>
        <Button variant="outline" size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Add Relationship
        </Button>
      </CardHeader>
      <CardContent>
        {(!relationships || relationships.length === 0) ? (
          <div className="text-center py-8 text-muted-foreground">
            <Link2 className="mx-auto h-8 w-8 text-muted-foreground/40" />
            <p className="mt-2 text-sm">No relationships defined</p>
          </div>
        ) : (
          <div className="divide-y">
            {relationships.map((rel) => (
              <RelationshipRow
                key={rel.id}
                rel={rel}
                moleculeId={moleculeId}
                onDelete={() => deleteMutation.mutate(rel.id)}
                isDeleting={deleteMutation.isPending}
              />
            ))}
          </div>
        )}
      </CardContent>

      <AddRelationshipDialog
        moleculeId={moleculeId}
        open={addOpen}
        onOpenChange={setAddOpen}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// RelationshipRow
// ---------------------------------------------------------------------------

function RelationshipRow({
  rel,
  moleculeId,
  onDelete,
  isDeleting,
}: {
  rel: {
    id: string;
    source_molecule_id: string;
    target_molecule_id: string;
    relationship_type: string;
    notes: string | null;
    created_at: string;
  };
  moleculeId: string;
  onDelete: () => void;
  isDeleting: boolean;
}) {
  const otherId =
    rel.source_molecule_id === moleculeId
      ? rel.target_molecule_id
      : rel.source_molecule_id;
  const { data: other } = useMolecule(otherId);

  return (
    <div className="flex items-center gap-3 py-3 group">
      <Badge variant="outline" className="shrink-0">
        {TYPE_LABEL[rel.relationship_type] ?? rel.relationship_type}
      </Badge>
      <Link
        href={`/compounds/${otherId}`}
        className="text-sm font-mono text-primary hover:underline"
      >
        {other?.registration_number ?? otherId.slice(0, 8)}
      </Link>
      {other?.name && (
        <span className="text-sm text-muted-foreground truncate">
          {other.name}
        </span>
      )}
      {rel.notes && (
        <span className="text-xs text-muted-foreground truncate ml-auto mr-2">
          {rel.notes}
        </span>
      )}
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 opacity-0 group-hover:opacity-100 shrink-0"
        onClick={onDelete}
        disabled={isDeleting}
      >
        <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AddRelationshipDialog
// ---------------------------------------------------------------------------

function AddRelationshipDialog({
  moleculeId,
  open,
  onOpenChange,
}: {
  moleculeId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const createMutation = useCreateRelationship(moleculeId);
  const [type, setType] = useState("");
  const [targetId, setTargetId] = useState("");
  const [notes, setNotes] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const { data: searchResults, isLoading: searching } = useMoleculeSearch(searchQuery);

  const filtered = searchResults?.filter((m) => m.id !== moleculeId);

  const reset = () => {
    setType("");
    setTargetId("");
    setNotes("");
    setSearchQuery("");
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Relationship</DialogTitle>
          <DialogDescription>
            Define a relationship to another compound.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Relationship type */}
          <div className="space-y-2">
            <Label>Relationship Type</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger>
                <SelectValue placeholder="Select type..." />
              </SelectTrigger>
              <SelectContent>
                {RELATIONSHIP_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Target molecule search */}
          <div className="space-y-2">
            <Label>Target Compound</Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by name or reg number..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setTargetId("");
                }}
                className="pl-8"
              />
            </div>
            {searching && <Skeleton className="h-8 w-full" />}
            {filtered && filtered.length > 0 && !targetId && (
              <div className="max-h-40 overflow-y-auto rounded-md border">
                {filtered.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className="w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center gap-2"
                    onClick={() => {
                      setTargetId(m.id);
                      setSearchQuery(m.registration_number || m.name || m.id);
                    }}
                  >
                    <span className="font-mono">{m.registration_number}</span>
                    {m.name && (
                      <span className="text-muted-foreground truncate">{m.name}</span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Notes */}
          <div className="space-y-2">
            <Label>Notes (optional)</Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="e.g. active metabolite detected in Phase I"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!type || !targetId || createMutation.isPending}
            onClick={() => {
              createMutation.mutate(
                {
                  target_molecule_id: targetId,
                  relationship_type: type,
                  notes: notes.trim() || undefined,
                },
                {
                  onSuccess: () => {
                    reset();
                    onOpenChange(false);
                  },
                }
              );
            }}
          >
            {createMutation.isPending ? "Adding..." : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
