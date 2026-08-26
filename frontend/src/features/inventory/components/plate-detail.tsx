"use client";

import { AttachmentList, FileUploadZone } from "@/features/attachment";
import { useProject } from "@/features/research-organization/hooks/use-projects";
import { usePlateTemplate } from "@/features/screening-assay/hooks/use-plate-templates";
import { WELL_TYPE_LABELS, type WellType } from "@/features/screening-assay/types";
import { TagTable } from "@/features/tagging/components/tag-table";
import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import { StatusBadge } from "@/shared/components/status-badge";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
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
import { useOrgs } from "@/shared/hooks/use-orgs";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { formatDate, formatDue } from "@/shared/lib/format-date";
import { formatStatusLabel } from "@/shared/lib/status-variants";
import { showError } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import { useAuthzHasRole } from "@duar-auth/nextjs";
import { Archive, ArrowLeftRight, MapPin, MoreHorizontal, Snowflake } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { usePlateGroup } from "../hooks/use-plate-groups";
import { LOAN_VARIANT, buildCustodyMap, useLoans } from "../hooks/use-plate-loans";
import {
  useChangeStatus,
  useDeletePlate,
  useDerivePlate,
  usePlate,
  usePlateChildren,
} from "../hooks/use-plates";
import { useStorageLocations } from "../hooks/use-storage-locations";
import { downloadPlateLayout } from "../lib/download-plate-layout";
import { type Whereabouts, plateWhereabouts } from "../lib/plate-where";
import type { PlateType, WellMapping } from "../types/plates";
import { plateTypeLabels } from "../types/plates";
import { CommentFeed } from "./comment-feed";
import { RequestLoanDialog } from "./request-loan-dialog";
import { WellMappingDialog } from "./well-mapping-dialog";

// ---------------------------------------------------------------------------
// ID → name resolver helpers
// ---------------------------------------------------------------------------

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
    <Link href={`/inventory/plates/${id}`} className="text-primary hover:underline font-mono">
      {parent ? parent.barcode : "View parent"}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Well grid visualization
// ---------------------------------------------------------------------------

function wellTypeColor(well: WellMapping): string {
  switch (well.well_type) {
    case "positive_control":
      return "bg-emerald-500/70";
    case "negative_control":
      return "bg-rose-500/70";
    case "blank":
      return "bg-slate-400/60";
    case "reference":
      return "bg-amber-500/70";
    default:
      return well.batch_id ? "bg-primary/60" : "bg-muted";
  }
}

interface WellMapProps {
  wellMap: Record<string, WellMapping>;
  format: string;
}

function WellMapVisualization({ wellMap, format }: WellMapProps) {
  const fmt = Number.parseInt(format, 10);

  // Determine rows/cols based on format
  let rows = 8;
  let cols = 12;
  if (fmt === 6) {
    rows = 2;
    cols = 3;
  } else if (fmt === 12) {
    rows = 3;
    cols = 4;
  } else if (fmt === 24) {
    rows = 4;
    cols = 6;
  } else if (fmt === 48) {
    rows = 6;
    cols = 8;
  } else if (fmt === 96) {
    rows = 8;
    cols = 12;
  } else if (fmt === 384) {
    rows = 16;
    cols = 24;
  } else if (fmt === 1536) {
    rows = 32;
    cols = 48;
  }

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
                title={
                  well
                    ? `${pos} · ${WELL_TYPE_LABELS[(well.well_type ?? "sample") as WellType]}${well.concentration_value != null ? ` · ${well.concentration_value} ${well.concentration_unit ?? ""}` : ""}`
                    : pos
                }
                className={cn(
                  cellSize,
                  "rounded-sm",
                  well ? wellTypeColor(well) : "bg-muted/40 border border-muted",
                )}
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
// Whereabouts hero — the one line a chemist came for
// ---------------------------------------------------------------------------

function WhereaboutsHero({
  where,
  memberName,
}: {
  where: Whereabouts;
  memberName: (id: string) => string;
}) {
  if (where.kind === "custody") {
    const due = formatDue(where.loan.due_date);
    return (
      <div
        data-testid="plate-hero"
        className={cn(
          "flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-sm",
          where.overdue
            ? "border-destructive/40 bg-destructive/5"
            : "border-warning/40 bg-warning/10",
        )}
      >
        <ArrowLeftRight className="h-4 w-4 shrink-0" />
        <span className="font-medium">{formatStatusLabel(where.item.status)}</span>
        <span>· {memberName(where.loan.requested_by)}</span>
        <span className="text-muted-foreground">
          · since {formatDate(where.item.status_changed_at)}
        </span>
        {due ? (
          <span
            title={`Due ${formatDate(where.loan.due_date)}`}
            className={cn(where.overdue ? "font-medium text-destructive" : "text-muted-foreground")}
          >
            · {due.label}
          </span>
        ) : null}
        <Link
          href={`/inventory/loans/${where.loan.id}`}
          className="ml-auto text-primary hover:underline"
        >
          View loan →
        </Link>
      </div>
    );
  }
  if (where.kind === "terminal") {
    return (
      <div
        data-testid="plate-hero"
        className="flex items-center gap-2 text-sm text-muted-foreground"
      >
        <Archive className="h-4 w-4 shrink-0" />
        {formatStatusLabel(where.status)}
      </div>
    );
  }
  if (where.kind === "location") {
    return (
      <div data-testid="plate-hero" className="flex items-center gap-2 text-sm">
        <Snowflake className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span title={where.fullPath}>In storage · {where.heroPath}</span>
      </div>
    );
  }
  return (
    <div data-testid="plate-hero" className="flex items-center gap-2 text-sm text-muted-foreground">
      <MapPin className="h-4 w-4 shrink-0" />
      {formatStatusLabel(where.status)} · no storage location
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
  const plate = query.data;
  const { data: children } = usePlateChildren(plateId);
  // Every loan this plate appeared in (API orders desc): custody + history from one fetch.
  const { data: loans } = useLoans({ plate_id: plateId });
  const { data: locations } = useStorageLocations();
  const { data: orgs } = useOrgs();
  const groupQuery = usePlateGroup(plate?.group_id ?? undefined);
  const memberName = useMemberNames();
  const [wellMapOpen, setWellMapOpen] = useState(false);
  const [deriveOpen, setDeriveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [loanBarcodes, setLoanBarcodes] = useState<string[] | null>(null);
  const changeStatus = useChangeStatus(plateId);
  const deletePlate = useDeletePlate();
  const canEditTags = useAuthzHasRole("editor");

  const custody = useMemo(() => buildCustodyMap(loans ?? []).get(plateId), [loans, plateId]);
  const where = useMemo(
    () => (plate ? plateWhereabouts(plate, custody, locations) : null),
    [plate, custody, locations],
  );
  const groupPath = groupQuery.data
    ? [...groupQuery.data.ancestors.map((a) => a.name), groupQuery.data.group.name].join(" › ")
    : null;
  const ownerName = plate?.owner_org_id
    ? orgs?.find((o) => o.id === plate.owner_org_id)?.name
    : undefined;

  const handleExport = async (id: string, format: "csv" | "xlsx") => {
    try {
      await downloadPlateLayout(id, format);
    } catch (e) {
      showError(e instanceof Error ? e.message : "Export failed");
    }
  };

  return (
    <>
      <DetailShell
        query={query}
        backHref="/inventory/plates"
        backLabel="Back to Plates"
        title={(p) => p.barcode || "Plate"}
        notFoundMessage="Plate not found."
        actions={(p) => {
          const canLoan =
            where?.kind !== "custody" && p.status !== "depleted" && p.status !== "disposed";
          return (
            <>
              {canLoan ? (
                <Button size="sm" onClick={() => setLoanBarcodes([p.barcode])}>
                  Request loan
                </Button>
              ) : null}
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
                  <SelectItem value="__current__" disabled>
                    Change Status
                  </SelectItem>
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
                  {p.status === "depleted" && <SelectItem value="disposed">Dispose</SelectItem>}
                </SelectContent>
              </Select>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" aria-label="More actions">
                    <MoreHorizontal className="mr-1.5 h-3.5 w-3.5" />
                    More
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={() => setWellMapOpen(true)}
                    disabled={p.status === "disposed"}
                  >
                    Map wells
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => router.push("/inventory/plates/import")}>
                    Import data
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport(p.id, "csv")}>
                    Export CSV — round-trippable
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport(p.id, "xlsx")}>
                    Export Excel (.xlsx)
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => setDeriveOpen(true)}
                    disabled={p.status === "disposed"}
                  >
                    Derive daughter plate
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onClick={() => setDeleteOpen(true)}>
                    Delete plate
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          );
        }}
      >
        {(p) => {
          const wellCount = p.well_map ? Object.keys(p.well_map).length : 0;
          return (
            <>
              <div className="-mt-3 flex flex-col gap-3">
                {where ? <WhereaboutsHero where={where} memberName={memberName} /> : null}
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  {p.group_id && !groupQuery.isError ? (
                    <Link
                      href={`/inventory/plate-groups/${p.group_id}`}
                      className="text-primary hover:underline"
                    >
                      {groupPath ?? "…"}
                    </Link>
                  ) : null}
                  <span className="text-muted-foreground">{p.format}-well</span>
                  <Badge variant="outline">
                    {plateTypeLabels[p.plate_type as PlateType] ?? p.plate_type}
                  </Badge>
                  {ownerName ? <span className="text-muted-foreground">{ownerName}</span> : null}
                  {p.plate_label ? (
                    <span className="text-muted-foreground">{p.plate_label}</span>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                <div className="flex flex-col gap-6">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Details</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <MetaRow label="Project">
                        <ResolvedProject id={p.project_id ?? null} />
                      </MetaRow>
                      <MetaRow label="Template">
                        <ResolvedTemplate id={p.template_id ?? null} />
                      </MetaRow>
                      <MetaRow label="Parent Plate">
                        <ResolvedParentPlate id={p.parent_plate_id ?? null} />
                      </MetaRow>
                      <MetaRow label="Registered by">{memberName(p.registered_by)}</MetaRow>
                      {p.notes && (
                        <MetaRow label="Notes">
                          <span className="text-muted-foreground">{p.notes}</span>
                        </MetaRow>
                      )}
                    </CardContent>
                  </Card>

                  <TagTable entity="plates" entityId={plateId} canEdit={canEditTags} />

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
                              <StatusBadge status={child.status} className="ml-auto" />
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  )}

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Files</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <FileUploadZone entityType="plate" entityId={plateId} />
                      <AttachmentList entityType="plate" entityId={plateId} />
                    </CardContent>
                  </Card>
                </div>

                <div className="flex flex-col gap-6">
                  {wellCount > 0 && p.well_map ? (
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base">
                          Well Map{" "}
                          <span className="ml-1 text-sm font-normal text-muted-foreground">
                            ({wellCount} wells occupied)
                          </span>
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="overflow-auto">
                          <WellMapVisualization wellMap={p.well_map} format={p.format} />
                          <p className="mt-3 text-xs text-muted-foreground">
                            Colored wells have compound batches mapped. Hover a well for details.
                          </p>
                        </div>
                      </CardContent>
                    </Card>
                  ) : null}

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">History</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {loans && loans.length > 0 ? (
                        <ul className="divide-y rounded-md border" data-testid="loan-history">
                          {loans.map((loan) => {
                            const item = loan.items.find((i) => i.plate_id === plateId);
                            return (
                              <li key={loan.id}>
                                <Link
                                  href={`/inventory/loans/${loan.id}`}
                                  className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm hover:bg-accent"
                                >
                                  <span className="font-medium">
                                    {memberName(loan.requested_by)}
                                  </span>
                                  {item ? (
                                    <StatusBadge
                                      status={item.status}
                                      variant={LOAN_VARIANT[item.status]}
                                    />
                                  ) : null}
                                  <span className="text-muted-foreground">
                                    {formatDate(loan.created_at)}
                                    {loan.closed_at ? ` → ${formatDate(loan.closed_at)}` : ""}
                                  </span>
                                </Link>
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <p className="text-sm text-muted-foreground">Never loaned.</p>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Comments</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <CommentFeed
                        scope={{ targetType: "plate", targetId: plateId }}
                        canWrite={canEditTags}
                      />
                    </CardContent>
                  </Card>
                </div>
              </div>
            </>
          );
        }}
      </DetailShell>

      {query.data && (
        <WellMappingDialog
          open={wellMapOpen}
          onOpenChange={setWellMapOpen}
          plateId={plateId}
          format={query.data.format}
          initialWellMap={query.data.well_map ?? null}
        />
      )}
      <DerivePlateDialog parentPlateId={plateId} open={deriveOpen} onOpenChange={setDeriveOpen} />
      <RequestLoanDialog
        open={loanBarcodes !== null}
        onOpenChange={(o) => {
          if (!o) setLoanBarcodes(null);
        }}
        orgId={plate?.owner_org_id ?? undefined}
        initialBarcodes={loanBarcodes ?? undefined}
      />
      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete plate?"
        description={`This will permanently delete plate "${plate?.barcode ?? ""}" (${plate?.plate_label ?? ""}). Well mappings will be lost.`}
        isPending={deletePlate.isPending}
        onConfirm={() =>
          deletePlate.mutate(plateId, { onSuccess: () => router.push("/inventory/plates") })
        }
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
                {(Object.entries(plateTypeLabels) as [PlateType, string][]).map(([value, lbl]) => (
                  <SelectItem key={value} value={value}>
                    {lbl}
                  </SelectItem>
                ))}
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
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
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
                },
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
