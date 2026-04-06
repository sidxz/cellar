"use client";

import { useState } from "react";
import {
  Trash2,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { EntityLink } from "@/shared/components/entity-link";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Separator } from "@/shared/components/ui/separator";
import {
  useRelationships,
  useDeleteRelationship,
} from "../../hooks/use-molecules";
import {
  useDisclosuresForMolecule,
  useMergeHistory,
} from "../../hooks/use-disclosures";
import { SynthesisRouteList } from "../synthesis-route-list";
import type { Molecule } from "../../types";

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function disclosureStatusBadgeVariant(
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "disclosed":
    case "merged":
      return "default";
    case "pending":
    case "processing":
      return "secondary";
    case "conflict":
    case "rejected":
      return "destructive";
    default:
      return "outline";
  }
}

// ---------------------------------------------------------------------------
// HistoryTab
// ---------------------------------------------------------------------------

interface HistoryTabProps {
  moleculeId: string;
  molecule: Molecule;
}

export function HistoryTab({ moleculeId }: HistoryTabProps) {
  const { data: disclosures } = useDisclosuresForMolecule(moleculeId);
  const { data: mergeHistory } = useMergeHistory(moleculeId);
  const { data: relationships } = useRelationships(moleculeId);
  const deleteRelMutation = useDeleteRelationship(moleculeId);

  const [disclosuresOpen, setDisclosuresOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);

  return (
    <div className="space-y-6">
      {/* Synthesis Routes Section */}
      <Card>
        <CardHeader>
          <CardTitle>Synthesis Routes</CardTitle>
        </CardHeader>
        <CardContent>
          <SynthesisRouteList moleculeId={moleculeId} />
        </CardContent>
      </Card>

      {/* Relationships Section */}
      {relationships && relationships.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              Relationships
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({relationships.length})
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Related Compound</TableHead>
                    <TableHead>Notes</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {relationships.map((rel) => {
                    const relatedId =
                      rel.source_molecule_id === moleculeId
                        ? rel.target_molecule_id
                        : rel.source_molecule_id;
                    return (
                      <TableRow key={rel.id}>
                        <TableCell>
                          <Badge variant="outline">
                            {rel.relationship_type.replace(/_/g, " ")}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <EntityLink
                            type="compound"
                            id={relatedId}
                            label={relatedId.slice(0, 8)}
                          />
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {rel.notes ?? "\u2014"}
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                            onClick={() => deleteRelMutation.mutate(rel.id)}
                            disabled={deleteRelMutation.isPending}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      <Separator />

      {/* Disclosure History (collapsible) */}
      <div>
        <button
          type="button"
          className="flex w-full items-center gap-2 text-left"
          onClick={() => setDisclosuresOpen(!disclosuresOpen)}
        >
          {disclosuresOpen ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          <h2 className="text-lg font-semibold">
            Disclosure History
            {disclosures?.length ? (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({disclosures.length})
              </span>
            ) : null}
          </h2>
        </button>

        {disclosuresOpen && (
          <div className="mt-4 space-y-3 pl-6">
            {!disclosures?.length ? (
              <p className="text-sm text-muted-foreground">
                No disclosure requests.
              </p>
            ) : (
              disclosures.map((d) => (
                <div
                  key={d.id}
                  className="flex items-start gap-3 rounded-lg border p-3"
                >
                  <Badge variant={disclosureStatusBadgeVariant(d.status)}>
                    {d.status}
                  </Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-mono truncate">
                      {d.disclosed_smiles}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Requested {new Date(d.requested_at).toLocaleDateString()}
                      {d.resolved_at &&
                        ` \u2022 Resolved ${new Date(d.resolved_at).toLocaleDateString()}`}
                    </p>
                    {d.notes && (
                      <p className="text-xs text-muted-foreground mt-1">
                        {d.notes}
                      </p>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Merge History (collapsible) */}
      <div>
        <button
          type="button"
          className="flex w-full items-center gap-2 text-left"
          onClick={() => setMergeOpen(!mergeOpen)}
        >
          {mergeOpen ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          <h2 className="text-lg font-semibold">
            Merge History
            {mergeHistory?.length ? (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({mergeHistory.length})
              </span>
            ) : null}
          </h2>
        </button>

        {mergeOpen && (
          <div className="mt-4 space-y-3 pl-6">
            {!mergeHistory?.length ? (
              <p className="text-sm text-muted-foreground">
                No merge events.
              </p>
            ) : (
              mergeHistory.map((m) => (
                <div
                  key={m.id}
                  className="flex items-start gap-3 rounded-lg border p-3"
                >
                  <Badge variant="outline">Merge</Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">
                      {m.reason}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {new Date(m.merged_at).toLocaleDateString()}
                      {" \u2022 "}
                      Source: <span className="font-mono">{m.source_molecule_id.slice(0, 8)}</span>
                      {" \u2192 "}
                      Target: <span className="font-mono">{m.target_molecule_id.slice(0, 8)}</span>
                    </p>
                    {m.notes && (
                      <p className="text-xs text-muted-foreground mt-1">
                        {m.notes}
                      </p>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
