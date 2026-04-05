"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  FlaskConical,
  ExternalLink,
} from "lucide-react";
import { StructureRenderer } from "@/shared/components/chemistry";
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
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Separator } from "@/shared/components/ui/separator";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  useMolecule,
  useAddIdentifier,
  useRemoveIdentifier,
  useRelationships,
  useDeleteRelationship,
} from "../hooks/use-molecules";
import { useDisclosuresForMolecule, useMergeHistory } from "../hooks/use-disclosures";
import { BatchList } from "@/features/inventory/components/batch-list";
import { SynthesisRouteList } from "./synthesis-route-list";
import {
  LIFECYCLE_LABELS,
  MOLECULE_TYPE_LABELS,
  type LifecycleStage,
  type MoleculeType,
  type StructureStatus,
} from "../types";
// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function lifecycleBadgeVariant(
  stage: LifecycleStage
): "default" | "secondary" | "destructive" | "outline" {
  switch (stage) {
    case "active":
    case "hit":
    case "lead":
      return "default";
    case "preclinical_candidate":
    case "development_candidate":
      return "secondary";
    case "deprioritized":
    case "archived":
      return "destructive";
    default:
      return "outline";
  }
}

function structureStatusBadgeClass(status: StructureStatus): string {
  return status === "disclosed"
    ? "border-emerald-500/40 text-emerald-400"
    : "border-yellow-500/40 text-yellow-400";
}

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
// Identifier type options
// ---------------------------------------------------------------------------

const IDENTIFIER_TYPES = [
  { value: "vendor_id", label: "Vendor ID" },
  { value: "cas_number", label: "CAS Number" },
  { value: "chembl_id", label: "ChEMBL ID" },
  { value: "pubchem_cid", label: "PubChem CID" },
  { value: "custom", label: "Custom" },
] as const;

// ---------------------------------------------------------------------------
// Descriptor display config
// ---------------------------------------------------------------------------

const DESCRIPTOR_FIELDS: Array<{
  key: string;
  label: string;
  format?: (v: number) => string;
}> = [
  { key: "molecular_weight", label: "MW", format: (v) => v.toFixed(2) },
  { key: "logp", label: "LogP", format: (v) => v.toFixed(2) },
  { key: "tpsa", label: "TPSA", format: (v) => v.toFixed(1) },
  { key: "hbd", label: "HBD" },
  { key: "hba", label: "HBA" },
  { key: "rotatable_bonds", label: "Rotatable Bonds" },
  { key: "ring_count", label: "Ring Count" },
  { key: "aromatic_rings", label: "Aromatic Rings" },
  { key: "heavy_atom_count", label: "Heavy Atoms" },
  { key: "ro5_violations", label: "RO5 Violations" },
];

// ---------------------------------------------------------------------------
// Add Identifier inline form
// ---------------------------------------------------------------------------

function AddIdentifierForm({
  moleculeId,
  onDone,
}: {
  moleculeId: string;
  onDone: () => void;
}) {
  const [identifier, setIdentifier] = useState("");
  const [identifierType, setIdentifierType] = useState("");
  const [source, setSource] = useState("");
  const addMutation = useAddIdentifier(moleculeId);

  const canSubmit = identifier.trim() && identifierType && source.trim();

  const handleSubmit = () => {
    if (!canSubmit) return;
    addMutation.mutate(
      {
        identifier: identifier.trim(),
        identifier_type: identifierType,
        source: source.trim(),
      },
      {
        onSuccess: () => {
          setIdentifier("");
          setIdentifierType("");
          setSource("");
          onDone();
        },
      }
    );
  };

  return (
    <div className="flex items-end gap-2 rounded-lg border border-dashed p-3">
      <div className="flex-1 space-y-1">
        <label className="text-xs text-muted-foreground">Identifier</label>
        <Input
          placeholder="e.g. CHEMBL25"
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
        <label className="text-xs text-muted-foreground">Source</label>
        <Input
          placeholder="e.g. ChEMBL"
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
      <Button
        size="sm"
        variant="ghost"
        className="h-8"
        onClick={onDone}
      >
        Cancel
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CompoundDetail
// ---------------------------------------------------------------------------

interface CompoundDetailProps {
  compoundId: string;
}

export function CompoundDetail({ compoundId }: CompoundDetailProps) {
  const router = useRouter();
  const { data: mol, isLoading } = useMolecule(compoundId);
  const { data: disclosures } = useDisclosuresForMolecule(compoundId);
  const { data: mergeHistory } = useMergeHistory(compoundId);
  const { data: relationships } = useRelationships(compoundId);
  const removeMutation = useRemoveIdentifier(compoundId);
  const deleteRelMutation = useDeleteRelationship(compoundId);

  const [showAddId, setShowAddId] = useState(false);
  const [disclosuresOpen, setDisclosuresOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);

  // --- Loading ---
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  // --- Not found ---
  if (!mol) {
    return (
      <div className="text-center text-muted-foreground py-12">
        <FlaskConical className="mx-auto h-12 w-12 text-muted-foreground/40" />
        <p className="mt-4">Compound not found.</p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-4"
          onClick={() => router.back()}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to compounds
        </Button>
      </div>
    );
  }

  const isTombstone = !!mol.merged_into_id;
  const isDisclosed = mol.structure_status === "disclosed";
  const descriptors = mol.descriptors;

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.back()}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to compounds
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight font-mono">
              {mol.registration_number}
            </h1>
            <Badge variant={lifecycleBadgeVariant(mol.lifecycle_stage as LifecycleStage)}>
              {LIFECYCLE_LABELS[mol.lifecycle_stage as LifecycleStage] ?? mol.lifecycle_stage}
            </Badge>
            <Badge variant="outline" className={structureStatusBadgeClass(mol.structure_status as StructureStatus)}>
              {mol.structure_status === "disclosed" ? "Disclosed" : "Undisclosed"}
            </Badge>
            <Badge variant="outline">
              {MOLECULE_TYPE_LABELS[mol.molecule_type as MoleculeType] ?? mol.molecule_type}
            </Badge>
          </div>
          {mol.name && (
            <p className="mt-1 text-lg text-muted-foreground">{mol.name}</p>
          )}
        </div>
      </div>

      {/* Tombstone banner */}
      {isTombstone && (
        <div className="flex items-center gap-3 rounded-lg border border-yellow-500/40 bg-yellow-500/10 p-4">
          <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium text-yellow-400">
              This compound has been merged.
            </p>
            <p className="text-sm text-muted-foreground">
              All data has been moved to the target compound.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              router.push(`/compounds/${mol.merged_into_id}`);
            }}
          >
            View target
            <ExternalLink className="ml-2 h-3 w-3" />
          </Button>
        </div>
      )}

      {/* Structure Card */}
      <Card>
        <CardHeader>
          <CardTitle>Structure</CardTitle>
        </CardHeader>
        <CardContent>
          {isDisclosed && mol.structure?.smiles ? (
            <div className="flex justify-center">
              <StructureRenderer
                smiles={mol.structure.smiles}
                width={400}
                height={280}
              />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
              <FlaskConical className="h-12 w-12 text-muted-foreground/40" />
              <p className="mt-4 text-sm text-muted-foreground">
                Undisclosed structure
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Properties Card */}
      <Card>
        <CardHeader>
          <CardTitle>Properties</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
            <div>
              <p className="text-sm text-muted-foreground">Formula</p>
              <p className="font-mono font-medium">
                {mol.molecular_formula ?? "\u2014"}
              </p>
            </div>
            {DESCRIPTOR_FIELDS.map((field) => {
              const raw = descriptors?.[field.key as keyof typeof descriptors];
              const value =
                raw != null
                  ? field.format
                    ? field.format(raw as number)
                    : String(raw)
                  : "\u2014";
              return (
                <div key={field.key}>
                  <p className="text-sm text-muted-foreground">{field.label}</p>
                  <p className="font-medium">{value}</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Identifiers Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Identifiers</CardTitle>
            {!showAddId && (
              <Button size="sm" variant="outline" onClick={() => setShowAddId(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Identifier
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {showAddId && (
            <AddIdentifierForm
              moleculeId={compoundId}
              onDone={() => setShowAddId(false)}
            />
          )}

          {mol.identifiers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No external identifiers registered.
            </p>
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
                  {mol.identifiers.map((ident) => (
                    <TableRow key={ident.id}>
                      <TableCell>
                        <Badge variant="outline">
                          {IDENTIFIER_TYPES.find((t) => t.value === ident.identifier_type)?.label ??
                            ident.identifier_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-sm">
                        {ident.identifier}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {ident.source || "\u2014"}
                      </TableCell>
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

      {/* Batches Section */}
      <Card>
        <CardHeader>
          <CardTitle>Batches</CardTitle>
        </CardHeader>
        <CardContent>
          <BatchList moleculeId={compoundId} />
        </CardContent>
      </Card>

      {/* Synthesis Routes Section */}
      <Card>
        <CardHeader>
          <CardTitle>Synthesis Routes</CardTitle>
        </CardHeader>
        <CardContent>
          <SynthesisRouteList moleculeId={compoundId} />
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
                      rel.source_molecule_id === compoundId
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
