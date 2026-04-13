"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Copy, FileUp, FlaskConical, Grid3x3 } from "lucide-react";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { DetailShell } from "@/shared/components/detail-shell";
import { AttachmentList, FileUploadZone } from "@/features/attachment";
import { usePlate, usePlateChildren, useChangeStatus, useDerivePlate } from "../hooks/use-plates";
import type { PlateStatus, PlateType, WellMapping } from "../types/plates";
import { plateTypeLabels, plateStatusLabels } from "../types/plates";
import { WellMappingDialog } from "./well-mapping-dialog";
import { useStorageLocations } from "../hooks/use-storage-locations";
import { usePlateTemplate } from "@/features/screening-assay/hooks/use-plate-templates";
import { useProject } from "@/features/research-organization/hooks/use-projects";

// ---------------------------------------------------------------------------
// ID → name resolver helpers
// ---------------------------------------------------------------------------

function ResolvedStorageLocation({ id }: { id: string | null }) {
  const { data: locations } = useStorageLocations();
  if (!id) return <span className="text-muted-foreground">Not set</span>;
  if (!locations) return <span className="text-muted-foreground">Loading...</span>;
  const loc = locations.find((l) => l.id === id);
  return <span>{loc?.name ?? id}</span>;
}

function ResolvedProject({ id }: { id: string | null }) {
  const { data: project } = useProject(id ?? undefined);
  if (!id) return <span className="text-muted-foreground">Not set</span>;
  if (!project) return <span className="text-muted-foreground">Loading...</span>;
  return <span>{project.name}</span>;
}

function ResolvedTemplate({ id }: { id: string | null }) {
  const { data: template } = usePlateTemplate(id ?? undefined);
  if (!id) return <span className="text-muted-foreground">None</span>;
  if (!template) return <span className="text-muted-foreground">Loading...</span>;
  return <span>{template.name}</span>;
}

function ResolvedParentPlate({ id }: { id: string | null }) {
  const { data: parent } = usePlate(id ?? undefined);
  if (!id) return <span className="text-muted-foreground">None</span>;
  return (
    <Link
      href={`/inventory/plates/${id}`}
      className="text-primary hover:underline font-mono"
    >
      {parent ? parent.barcode : "View parent"}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function plateStatusVariant(
  status: PlateStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "registered":
      return "outline";
    case "in_use":
      return "default";
    case "stored":
      return "secondary";
    case "depleted":
    case "disposed":
      return "destructive";
    default:
      return "outline";
  }
}

// ---------------------------------------------------------------------------
// Well grid visualization
// ---------------------------------------------------------------------------

function wellTypeColor(well: WellMapping): string {
  if (!well.concentration_value) return "bg-muted";
  return "bg-primary/60";
}

interface WellMapProps {
  wellMap: Record<string, WellMapping>;
  format: string;
}

function WellMapVisualization({ wellMap, format }: WellMapProps) {
  const fmt = parseInt(format, 10);

  // Determine rows/cols based on format
  let rows = 8;
  let cols = 12;
  if (fmt === 6) { rows = 2; cols = 3; }
  else if (fmt === 12) { rows = 3; cols = 4; }
  else if (fmt === 24) { rows = 4; cols = 6; }
  else if (fmt === 48) { rows = 6; cols = 8; }
  else if (fmt === 96) { rows = 8; cols = 12; }
  else if (fmt === 384) { rows = 16; cols = 24; }
  else if (fmt === 1536) { rows = 32; cols = 48; }

  const rowLetters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".slice(0, rows).split("");

  const cellSize = fmt > 384 ? "h-1 w-1" : fmt > 96 ? "h-2 w-2" : "h-4 w-4";
  const gap = fmt > 384 ? "gap-px" : "gap-0.5";

  return (
    <div className={`flex flex-col ${gap}`}>
      {rowLetters.map((row) => (
        <div key={row} className={`flex ${gap}`}>
          {Array.from({ length: cols }, (_, i) => {
            const pos = `${row}${i + 1}`;
            const well = wellMap[pos];
            return (
              <div
                key={pos}
                title={well ? `${pos}: ${well.concentration_value ?? "—"} ${well.concentration_unit ?? ""}` : pos}
                className={`${cellSize} rounded-sm ${well ? wellTypeColor(well) : "bg-muted/40 border border-muted"}`}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metadata row helper
// ---------------------------------------------------------------------------

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
      <span className="w-40 shrink-0 text-sm text-muted-foreground">{label}</span>
      <span className="text-sm">{children}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PlateDetail
// ---------------------------------------------------------------------------

interface PlateDetailProps {
  plateId: string;
}

export function PlateDetail({ plateId }: PlateDetailProps) {
  const router = useRouter();
  const query = usePlate(plateId);
  const { data: children } = usePlateChildren(plateId);
  const [wellMapOpen, setWellMapOpen] = useState(false);
  const [deriveOpen, setDeriveOpen] = useState(false);
  const changeStatus = useChangeStatus(plateId);

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/plates"
        backLabel="Back to Plates"
        title={(p) => p.barcode || "Plate"}
        notFoundMessage="Plate not found."
        actions={(p) => (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setWellMapOpen(true)}
              disabled={p.status === "disposed"}
            >
              <Grid3x3 className="mr-1.5 h-3.5 w-3.5" />
              Map Wells
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/inventory/plates/import")}
            >
              <FileUp className="mr-1.5 h-3.5 w-3.5" />
              Import Data
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeriveOpen(true)}
              disabled={p.status === "disposed"}
            >
              <Copy className="mr-1.5 h-3.5 w-3.5" />
              Derive Plate
            </Button>
            <Select
              value="__current__"
              onValueChange={(v) => {
                if (v !== "__current__") changeStatus.mutate(v);
              }}
            >
              <SelectTrigger className="h-8 w-[150px] text-xs">
                <SelectValue>Change Status</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__current__" disabled>Change Status</SelectItem>
                {p.status === "registered" && (
                  <>
                    <SelectItem value="stored">Store</SelectItem>
                    <SelectItem value="in_use">Check Out</SelectItem>
                    <SelectItem value="disposed">Dispose</SelectItem>
                  </>
                )}
                {p.status === "in_use" && (
                  <>
                    <SelectItem value="stored">Return to Storage</SelectItem>
                    <SelectItem value="depleted">Mark Depleted</SelectItem>
                  </>
                )}
                {p.status === "stored" && (
                  <>
                    <SelectItem value="in_use">Check Out</SelectItem>
                    <SelectItem value="depleted">Mark Depleted</SelectItem>
                    <SelectItem value="disposed">Dispose</SelectItem>
                  </>
                )}
                {p.status === "depleted" && (
                  <SelectItem value="disposed">Dispose</SelectItem>
                )}
              </SelectContent>
            </Select>
          </>
        )}
      >
        {(plate) => {
          const wellCount = plate.well_map ? Object.keys(plate.well_map).length : 0;
          return (
            <>
      <div className="flex flex-wrap items-center gap-2 -mt-3">
        <Badge variant={plateStatusVariant(plate.status as PlateStatus)}>
          {plateStatusLabels[plate.status as PlateStatus] ?? plate.status}
        </Badge>
        <Badge variant="outline">
          {plateTypeLabels[plate.plate_type as PlateType] ?? plate.plate_type}
        </Badge>
        {plate.plate_label && (
          <span className="text-muted-foreground">{plate.plate_label}</span>
        )}
      </div>

      {/* Metadata card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <MetaRow label="Format">{plate.format}-well</MetaRow>
          <MetaRow label="Wells Mapped">
            {wellCount > 0 ? (
              <span>
                {wellCount} / {plate.format} wells
              </span>
            ) : (
              <span className="text-muted-foreground">None</span>
            )}
          </MetaRow>
          <MetaRow label="Storage Location">
            <ResolvedStorageLocation id={plate.storage_location_id} />
          </MetaRow>
          <MetaRow label="Project">
            <ResolvedProject id={plate.project_id} />
          </MetaRow>
          <MetaRow label="Template">
            <ResolvedTemplate id={plate.template_id} />
          </MetaRow>
          <MetaRow label="Parent Plate">
            <ResolvedParentPlate id={plate.parent_plate_id} />
          </MetaRow>
          {plate.notes && (
            <MetaRow label="Notes">
              <span className="text-muted-foreground">{plate.notes}</span>
            </MetaRow>
          )}
        </CardContent>
      </Card>

      {/* Well map visualization */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Well Map{" "}
            {wellCount > 0 && (
              <span className="ml-1 text-sm font-normal text-muted-foreground">
                ({wellCount} wells occupied)
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {wellCount > 0 && plate.well_map ? (
            <div className="overflow-auto">
              <WellMapVisualization
                wellMap={plate.well_map}
                format={plate.format}
              />
              <p className="mt-3 text-xs text-muted-foreground">
                Colored wells have compound batches mapped. Hover a well for details.
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
              <FlaskConical className="h-8 w-8 text-muted-foreground/40" />
              <p className="mt-2 text-sm text-muted-foreground">
                No wells mapped yet.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Children plates */}
      {children && children.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Daughter Plates ({children.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {children.map((child) => (
                <li key={child.id} className="flex items-center gap-3">
                  <Link
                    href={`/inventory/plates/${child.id}`}
                    className="font-mono text-sm text-primary hover:underline"
                  >
                    {child.barcode}
                  </Link>
                  <span className="text-sm text-muted-foreground">
                    {child.plate_label}
                  </span>
                  <Badge variant={plateStatusVariant(child.status as PlateStatus)} className="ml-auto">
                    {plateStatusLabels[child.status as PlateStatus] ?? child.status}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Attachments */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Files</CardTitle>
        </CardHeader>
        <CardContent>
          <FileUploadZone entityType="plate" entityId={plateId} />
          <AttachmentList entityType="plate" entityId={plateId} />
        </CardContent>
      </Card>
            </>
          );
        }}
      </DetailShell>

      {/* Well mapping dialog */}
      {query.data && (
        <WellMappingDialog
          open={wellMapOpen}
          onOpenChange={setWellMapOpen}
          plateId={plateId}
          format={query.data.format}
          initialWellMap={query.data.well_map}
        />
      )}

      {/* Derive plate dialog */}
      <DerivePlateDialog
        parentPlateId={plateId}
        open={deriveOpen}
        onOpenChange={setDeriveOpen}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// DerivePlateDialog
// ---------------------------------------------------------------------------

function DerivePlateDialog({
  parentPlateId,
  open,
  onOpenChange,
}: {
  parentPlateId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const deriveMutation = useDerivePlate(parentPlateId);
  const { data: locations } = useStorageLocations();
  const [barcode, setBarcode] = useState("");
  const [label, setLabel] = useState("");
  const [plateType, setPlateType] = useState<string>("daughter");
  const [storageId, setStorageId] = useState("");
  const [notes, setNotes] = useState("");

  const reset = () => {
    setBarcode("");
    setLabel("");
    setPlateType("daughter");
    setStorageId("");
    setNotes("");
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
          <DialogTitle>Derive Daughter Plate</DialogTitle>
          <DialogDescription>
            Create a new plate from this parent. The well map will be copied.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Barcode *</Label>
            <Input
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
              placeholder="e.g. PL-2026-0501"
            />
          </div>
          <div className="space-y-2">
            <Label>Label *</Label>
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Daughter plate for screen #3"
            />
          </div>
          <div className="space-y-2">
            <Label>Plate Type</Label>
            <Select value={plateType} onValueChange={setPlateType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.entries(plateTypeLabels) as [PlateType, string][]).map(
                  ([value, lbl]) => (
                    <SelectItem key={value} value={value}>
                      {lbl}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Storage Location</Label>
            <Select value={storageId} onValueChange={setStorageId}>
              <SelectTrigger>
                <SelectValue placeholder="Select location..." />
              </SelectTrigger>
              <SelectContent>
                {locations?.map((loc) => (
                  <SelectItem key={loc.id} value={loc.id}>
                    {loc.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Notes</Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!barcode.trim() || !label.trim() || deriveMutation.isPending}
            onClick={() => {
              deriveMutation.mutate(
                {
                  barcode: barcode.trim(),
                  plate_label: label.trim(),
                  plate_type: plateType,
                  storage_location_id: storageId || null,
                  notes: notes.trim() || null,
                },
                {
                  onSuccess: (newPlate) => {
                    reset();
                    onOpenChange(false);
                    router.push(`/inventory/plates/${newPlate.id}`);
                  },
                }
              );
            }}
          >
            {deriveMutation.isPending ? "Creating..." : "Derive"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
