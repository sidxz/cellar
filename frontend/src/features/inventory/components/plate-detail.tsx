"use client";

import Link from "next/link";
import { ArrowLeft, FlaskConical } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { usePlate, usePlateChildren } from "../hooks/use-plates";
import type { PlateStatus, PlateType, WellMapping } from "../types/plates";
import { plateTypeLabels, plateStatusLabels } from "../types/plates";

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
  const { data: plate, isLoading } = usePlate(plateId);
  const { data: children } = usePlateChildren(plateId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!plate) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <FlaskConical className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Plate not found</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          The plate may have been deleted or does not exist.
        </p>
        <Button variant="outline" className="mt-4" asChild>
          <Link href="/inventory/plates">Back to Plates</Link>
        </Button>
      </div>
    );
  }

  const wellCount = plate.well_map ? Object.keys(plate.well_map).length : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/inventory/plates">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-2xl font-bold tracking-tight">
              {plate.barcode}
            </h1>
            <Badge variant={plateStatusVariant(plate.status as PlateStatus)}>
              {plateStatusLabels[plate.status as PlateStatus] ?? plate.status}
            </Badge>
            <Badge variant="outline">
              {plateTypeLabels[plate.plate_type as PlateType] ?? plate.plate_type}
            </Badge>
          </div>
          <p className="mt-1 text-muted-foreground">{plate.plate_label}</p>
        </div>
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
            {plate.storage_location_id ?? (
              <span className="text-muted-foreground">Not set</span>
            )}
          </MetaRow>
          <MetaRow label="Project">
            {plate.project_id ?? (
              <span className="text-muted-foreground">Not set</span>
            )}
          </MetaRow>
          <MetaRow label="Template">
            {plate.template_id ?? (
              <span className="text-muted-foreground">None</span>
            )}
          </MetaRow>
          <MetaRow label="Parent Plate">
            {plate.parent_plate_id ? (
              <Link
                href={`/inventory/plates/${plate.parent_plate_id}`}
                className="text-primary hover:underline font-mono"
              >
                View parent
              </Link>
            ) : (
              <span className="text-muted-foreground">None</span>
            )}
          </MetaRow>
          <MetaRow label="Registered By">
            {plate.registered_by ? (
              <span className="font-mono text-xs">{plate.registered_by}</span>
            ) : (
              <span className="text-muted-foreground">\u2014</span>
            )}
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
    </div>
  );
}
