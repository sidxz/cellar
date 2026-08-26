"use client";

import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { showError } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import type { ColDef } from "ag-grid-community";
import { FileUp, FlaskConical, Plus, Settings } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useGroupIndex } from "../hooks/use-plate-groups";
import { buildCustodyMap, useLoans } from "../hooks/use-plate-loans";
import { usePlates } from "../hooks/use-plates";
import { useStorageLocations } from "../hooks/use-storage-locations";
import {
  PLATE_CHIP_LABELS,
  PLATE_CHIP_ORDER,
  type PlateChipKey,
  type WhereTone,
  type Whereabouts,
  plateChipKeys,
  plateWhereabouts,
  whereText,
} from "../lib/plate-where";
import type { PlateStatus, PlateType, RegisteredPlate } from "../types/plates";
import { plateStatusLabels, plateTypeLabels } from "../types/plates";
import { CountChips } from "./count-chips";
import { OrgPlatePolicyDialog } from "./org-plate-policy-dialog";
import { RegisterPlateDialog } from "./register-plate-dialog";
import { RequestLoanDialog } from "./request-loan-dialog";

/** Filter sentinel: scope the plate list to the current user's own org. */
const MY_ORG = "__mine__";
/** Filter sentinel: no org scoping — show plates from every org (admin-only selector). */
const ALL_ORGS = "__all__";
/** Admin's last org choice survives navigation (P5). */
const ORG_STORAGE_KEY = "plates.org";

const PLATE_FORMATS = ["6", "12", "24", "48", "96", "384", "1536"] as const;

/** Spec X2: colour only exceptions. */
export const TONE_CLASS: Record<WhereTone, string> = {
  overdue: "font-medium text-destructive",
  loan: "text-warning",
  muted: "text-muted-foreground",
  normal: "",
};

interface PlateRow {
  plate: RegisteredPlate;
  where: Whereabouts;
  chips: Set<PlateChipKey>;
}

export function PlateList() {
  const router = useRouter();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [policyOpen, setPolicyOpen] = useState(false);
  const [loanBarcodes, setLoanBarcodes] = useState<string[] | null>(null);
  const [filterType, setFilterType] = useState<string>("__all__");
  const [filterStatus, setFilterStatus] = useState<string>("__all__");
  const [filterFormat, setFilterFormat] = useState<string>("__all__");
  const [filterOrg, setFilterOrg] = useState<string>(MY_ORG);
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const [chip, setChip] = useState<PlateChipKey | null>(null);

  const { data: me, isError: meFailed } = useCurrentUser();
  const isAdmin = me?.is_admin === true;
  const { data: orgs } = useOrgs();
  const memberName = useMemberNames();
  const { data: locations } = useStorageLocations();
  const orgNameById = useMemo(() => new Map((orgs ?? []).map((o) => [o.id, o.name])), [orgs]);
  // Open loans → plate_id custody lookup, for the Where column and the chips.
  const { data: openLoans } = useLoans({ status: "open" });
  const custodyByPlate = useMemo(() => buildCustodyMap(openLoans ?? []), [openLoans]);

  // Admins: restore the remembered org once we know they're an admin.
  useEffect(() => {
    if (!isAdmin) return;
    try {
      const stored = window.localStorage.getItem(ORG_STORAGE_KEY);
      if (stored) setFilterOrg(stored);
    } catch {
      /* storage unavailable */
    }
  }, [isAdmin]);
  const selectOrg = (v: string) => {
    setFilterOrg(v);
    try {
      window.localStorage.setItem(ORG_STORAGE_KEY, v);
    } catch {
      /* storage unavailable */
    }
  };

  // "My org" needs /me. If /me failed, fall back to un-filtered (All orgs)
  // rather than gating the list forever behind a query that will never run.
  const ownerOrgId =
    filterOrg === MY_ORG
      ? meFailed
        ? undefined
        : (me?.org_id ?? undefined)
      : filterOrg === ALL_ORGS
        ? undefined
        : filterOrg;
  const allOrgs = filterOrg === ALL_ORGS;
  const groupOrgIds = useMemo(
    () => (allOrgs ? (orgs ?? []).map((o) => o.id) : ownerOrgId ? [ownerOrgId] : []),
    [allOrgs, orgs, ownerOrgId],
  );
  const groupIndex = useGroupIndex(groupOrgIds);

  const {
    data: plates,
    isLoading,
    error,
  } = usePlates(
    {
      plate_type: filterType === "__all__" ? undefined : filterType,
      status: filterStatus === "__all__" ? undefined : filterStatus,
      format: filterFormat === "__all__" ? undefined : filterFormat,
      owner_org_id: ownerOrgId,
      tags: tagFilter.tagIds,
      tagLogic: tagFilter.tagLogic,
    },
    // Hold the fetch until /me resolves while "My org" is active — otherwise
    // the grid flashes all-orgs data during the identity load.
    { enabled: filterOrg !== MY_ORG || me !== undefined || meFailed },
  );

  useEffect(() => {
    if (meFailed && filterOrg === MY_ORG) {
      showError("Could not resolve your organization — showing all orgs");
    }
  }, [meFailed, filterOrg]);

  const rows = useMemo<PlateRow[] | undefined>(
    () =>
      plates?.map((plate) => {
        const where = plateWhereabouts(plate, custodyByPlate.get(plate.id), locations);
        return { plate, where, chips: plateChipKeys(plate, where) };
      }),
    [plates, custodyByPlate, locations],
  );
  const chipCounts = useMemo(() => {
    const counts = Object.fromEntries(PLATE_CHIP_ORDER.map((k) => [k, 0])) as Record<
      PlateChipKey,
      number
    >;
    for (const r of rows ?? []) for (const k of r.chips) counts[k] += 1;
    return counts;
  }, [rows]);
  const visibleRows = useMemo(
    () => (chip ? rows?.filter((r) => r.chips.has(chip)) : rows),
    [rows, chip],
  );

  const columnDefs = useMemo<ColDef<PlateRow>[]>(
    () => [
      {
        headerName: "Barcode",
        field: "plate.barcode",
        flex: 1,
        minWidth: 140,
        cellRenderer: ({ data }: { data: PlateRow | undefined }) =>
          data ? (
            <button
              type="button"
              className="font-mono text-sm text-primary hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                router.push(`/inventory/plates/${data.plate.id}`);
              }}
            >
              {data.plate.barcode}
            </button>
          ) : null,
      },
      { headerName: "Name", field: "plate.plate_label", flex: 1, minWidth: 160 },
      {
        headerName: "Set",
        flex: 1.2,
        minWidth: 160,
        // Sort/quick-filter on the full path; the cell shows the leaf set name
        // (legacy paths run three levels deep and truncate), path on hover.
        valueGetter: (p) =>
          p.data?.plate.group_id ? (groupIndex.get(p.data.plate.group_id)?.path ?? "…") : "—",
        cellRenderer: ({ data }: { data: PlateRow | undefined }) => {
          if (!data?.plate.group_id) return "—";
          const ref = groupIndex.get(data.plate.group_id);
          return <span title={ref?.path}>{ref?.name ?? "…"}</span>;
        },
      },
      { headerName: "Format", field: "plate.format", width: 90 },
      {
        headerName: "Where",
        flex: 1.4,
        minWidth: 220,
        valueGetter: (p) => (p.data ? whereText(p.data.where, memberName).text : ""),
        cellRenderer: ({ data }: { data: PlateRow | undefined }) => {
          if (!data) return null;
          const t = whereText(data.where, memberName);
          return (
            <span title={t.title} className={cn(TONE_CLASS[t.tone])}>
              {t.text}
            </span>
          );
        },
      },
      {
        headerName: "Owner",
        hide: !allOrgs,
        width: 160,
        valueGetter: (p) =>
          p.data?.plate.owner_org_id
            ? (orgNameById.get(p.data.plate.owner_org_id) ?? (orgs ? "Unknown org" : "—"))
            : "—",
      },
    ],
    [router, orgNameById, orgs, allOrgs, groupIndex, memberName],
  );

  const header = (
    <PageHeader title="Plates" subtitle="Which set, where it is, who has it.">
      {isAdmin ? (
        <Button variant="outline" onClick={() => setPolicyOpen(true)}>
          <Settings className="mr-2 h-4 w-4" />
          Org Policies
        </Button>
      ) : null}
      <Button variant="outline" onClick={() => router.push("/inventory/plates/import")}>
        <FileUp className="mr-2 h-4 w-4" />
        Import Data
      </Button>
      <Button onClick={() => setRegisterOpen(true)}>
        <Plus className="mr-2 h-4 w-4" />
        Register Plate
      </Button>
    </PageHeader>
  );

  if (error) {
    return (
      <div>
        {header}
        <ErrorState
          message="Failed to load plates. Is the backend running?"
          details={error.message}
        />
      </div>
    );
  }

  const filtered =
    chip !== null ||
    filterType !== "__all__" ||
    filterStatus !== "__all__" ||
    filterFormat !== "__all__" ||
    tagFilter.tagIds.length > 0;
  const total = rows?.length ?? 0;

  return (
    <div>
      {header}

      {/* Filter bar */}
      <div className="mb-3 flex flex-wrap gap-2">
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger className="w-[170px]">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All types</SelectItem>
            {(Object.keys(plateTypeLabels) as PlateType[]).map((t) => (
              <SelectItem key={t} value={t}>
                {plateTypeLabels[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All statuses</SelectItem>
            {(Object.keys(plateStatusLabels) as PlateStatus[]).map((s) => (
              <SelectItem key={s} value={s}>
                {plateStatusLabels[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterFormat} onValueChange={setFilterFormat}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="All formats" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All formats</SelectItem>
            {PLATE_FORMATS.map((f) => (
              <SelectItem key={f} value={f}>
                {f}-well
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {isAdmin ? (
          <Select value={filterOrg} onValueChange={selectOrg}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="My org" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={MY_ORG}>
                {me?.org_slug ? `My org (${me.org_slug})` : "My org"}
              </SelectItem>
              <SelectItem value={ALL_ORGS}>All orgs</SelectItem>
              {orgs?.map((o) => (
                <SelectItem key={o.id} value={o.id}>
                  {o.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}

        <TagFilter value={tagFilter} onChange={setTagFilter} />
      </div>

      {/* Summary strip */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {total.toLocaleString("en-US")} plate{total === 1 ? "" : "s"}
        </span>
        <CountChips
          chips={PLATE_CHIP_ORDER.map((key) => ({
            key,
            label: PLATE_CHIP_LABELS[key],
            count: chipCounts[key],
            tone: key === "overdue" ? ("destructive" as const) : undefined,
          }))}
          active={chip}
          onChange={(k) => setChip(k as PlateChipKey | null)}
        />
      </div>

      <DataGrid<PlateRow>
        rowData={visibleRows}
        columnDefs={columnDefs}
        loading={isLoading || !plates}
        height="calc(100vh - 20rem)"
        suppressFilters
        preferencesKey="plates"
        getRowId={(p) => p.data.plate.id}
        onRowClick={(row) => router.push(`/inventory/plates/${row.plate.id}`)}
        selectionToolbar={(selected) => (
          <>
            <span className="text-sm text-muted-foreground">{selected.length} selected</span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setLoanBarcodes(selected.map((r) => r.plate.barcode))}
            >
              Request loan ({selected.length})
            </Button>
          </>
        )}
        emptyState={
          filtered ? (
            <p className="p-6 text-sm text-muted-foreground">
              No plates match the current filters.
            </p>
          ) : (
            <EmptyState
              icon={FlaskConical}
              title="No plates"
              description="Register a plate to start tracking compound locations."
              action={{ label: "Register Plate", onClick: () => setRegisterOpen(true), icon: Plus }}
            />
          )
        }
      />

      <RegisterPlateDialog open={registerOpen} onOpenChange={setRegisterOpen} />
      <OrgPlatePolicyDialog open={policyOpen} onOpenChange={setPolicyOpen} />
      <RequestLoanDialog
        open={loanBarcodes !== null}
        onOpenChange={(o) => {
          if (!o) setLoanBarcodes(null);
        }}
        orgId={me?.org_id ?? undefined}
        initialBarcodes={loanBarcodes ?? undefined}
      />
    </div>
  );
}
