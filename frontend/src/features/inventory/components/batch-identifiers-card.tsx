"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import {
  useAddBatchIdentifier,
  useBatchIdentifiers,
  useRemoveBatchIdentifier,
} from "../hooks/use-batch-identifiers";

// ---------------------------------------------------------------------------
// Identifier type options (batch-specific)
// ---------------------------------------------------------------------------

const IDENTIFIER_TYPES = [
  { value: "external_lot", label: "External Lot" },
  { value: "cdd_batch_id", label: "CDD Batch ID" },
  { value: "vendor_lot", label: "Vendor Lot" },
  { value: "custom", label: "Custom" },
] as const;

// ---------------------------------------------------------------------------
// Add Identifier inline form
// ---------------------------------------------------------------------------

function AddBatchIdentifierForm({
  batchId,
  onDone,
}: {
  batchId: string;
  onDone: () => void;
}) {
  const [identifier, setIdentifier] = useState("");
  const [identifierType, setIdentifierType] = useState("");
  const [source, setSource] = useState("");
  const addMutation = useAddBatchIdentifier(batchId);

  const canSubmit = identifier.trim() && identifierType;

  const handleSubmit = () => {
    if (!canSubmit) return;
    addMutation.mutate(
      {
        identifier: identifier.trim(),
        identifier_type: identifierType,
        source: source.trim() || "User added",
      },
      {
        onSuccess: () => {
          setIdentifier("");
          setIdentifierType("");
          setSource("");
          onDone();
        },
      },
    );
  };

  return (
    <div className="flex items-end gap-2 rounded-lg border border-dashed p-3">
      <div className="flex-1 space-y-1">
        <label className="text-xs text-muted-foreground">Identifier</label>
        <Input
          placeholder="e.g. LOT-2024-001"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          className="h-8"
        />
      </div>
      <div className="w-40 space-y-1">
        <label className="text-xs text-muted-foreground">Type</label>
        <Select value={identifierType} onValueChange={setIdentifierType}>
          <SelectTrigger className="h-8">
            <SelectValue placeholder="Select type" />
          </SelectTrigger>
          <SelectContent>
            {IDENTIFIER_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="w-36 space-y-1">
        <label className="text-xs text-muted-foreground">
          Source <span className="text-muted-foreground/60">(optional)</span>
        </label>
        <Input
          placeholder="e.g. CDD Vault"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="h-8"
        />
      </div>
      <Button
        size="sm"
        className="h-8"
        disabled={!canSubmit || addMutation.isPending}
        onClick={handleSubmit}
      >
        {addMutation.isPending ? "Adding..." : "Add"}
      </Button>
      <Button size="sm" variant="ghost" className="h-8" onClick={onDone}>
        Cancel
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BatchIdentifiersCard
// ---------------------------------------------------------------------------

interface BatchIdentifiersCardProps {
  batchId: string;
}

export function BatchIdentifiersCard({ batchId }: BatchIdentifiersCardProps) {
  const [showAddForm, setShowAddForm] = useState(false);
  const { data: identifiers = [] } = useBatchIdentifiers(batchId);
  const removeMutation = useRemoveBatchIdentifier(batchId);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Identifiers</CardTitle>
          {!showAddForm && (
            <Button size="sm" variant="outline" onClick={() => setShowAddForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Identifier
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {showAddForm && (
          <AddBatchIdentifierForm batchId={batchId} onDone={() => setShowAddForm(false)} />
        )}

        {identifiers.length === 0 ? (
          <p className="text-sm text-muted-foreground">No identifiers registered.</p>
        ) : (
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {identifiers.map((ident) => (
                  <TableRow key={ident.id}>
                    <TableCell>
                      <Badge variant="outline">
                        {IDENTIFIER_TYPES.find((t) => t.value === ident.identifier_type)?.label ??
                          ident.identifier_type}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{ident.identifier}</TableCell>
                    <TableCell className="text-muted-foreground">{ident.source || "—"}</TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => removeMutation.mutate(ident.id)}
                        disabled={removeMutation.isPending}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
