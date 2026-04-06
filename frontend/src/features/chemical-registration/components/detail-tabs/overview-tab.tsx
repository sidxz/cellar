"use client";

import { useState } from "react";
import {
  Plus,
  Trash2,
  FlaskConical,
  Copy,
  Check,
} from "lucide-react";
import { StructureRenderer } from "@/shared/components/chemistry";
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
import {
  useAddIdentifier,
  useRemoveIdentifier,
} from "../../hooks/use-molecules";
import type { Molecule } from "../../types";

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
// Copy-to-clipboard field
// ---------------------------------------------------------------------------

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex items-start gap-2 group">
      <span className="text-xs font-medium text-muted-foreground w-16 shrink-0 pt-0.5">
        {label}
      </span>
      <code className="flex-1 text-xs font-mono break-all text-muted-foreground/80">
        {value}
      </code>
      <button
        type="button"
        onClick={handleCopy}
        className="shrink-0 p-1 rounded hover:bg-muted transition-colors opacity-0 group-hover:opacity-100"
        title={`Copy ${label}`}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <Copy className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>
    </div>
  );
}

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
// OverviewTab
// ---------------------------------------------------------------------------

interface OverviewTabProps {
  molecule: Molecule;
  compoundId: string;
}

export function OverviewTab({ molecule, compoundId }: OverviewTabProps) {
  const [showAddId, setShowAddId] = useState(false);
  const removeMutation = useRemoveIdentifier(compoundId);

  const isDisclosed = molecule.structure_status === "disclosed";
  const descriptors = molecule.descriptors;

  return (
    <div className="space-y-6">
      {/* Structure Card */}
      <Card>
        <CardHeader>
          <CardTitle>Structure</CardTitle>
        </CardHeader>
        <CardContent>
          {isDisclosed && molecule.structure?.smiles ? (
            <>
              <div className="flex justify-center">
                <StructureRenderer
                  smiles={molecule.structure.smiles}
                  width={400}
                  height={280}
                />
              </div>
              <div className="mt-4 space-y-2">
                <CopyField label="SMILES" value={molecule.structure.smiles} />
                {molecule.structure.inchi && <CopyField label="InChI" value={molecule.structure.inchi} />}
                {molecule.structure.inchi_key && <CopyField label="InChI Key" value={molecule.structure.inchi_key} />}
              </div>
            </>
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
                {molecule.molecular_formula ?? "\u2014"}
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

          {molecule.identifiers.length === 0 ? (
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
                  {molecule.identifiers.map((ident) => (
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

      {/* Custom Fields */}
      {molecule.custom_fields && Object.keys(molecule.custom_fields).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Custom Fields</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
              {Object.entries(molecule.custom_fields).map(([key, value]) => (
                <div key={key}>
                  <p className="text-sm text-muted-foreground">
                    {key.replace(/_/g, " ")}
                  </p>
                  <p className="font-medium">{String(value ?? "\u2014")}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
