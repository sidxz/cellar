import { formatDate, formatDue } from "@/shared/lib/format-date";
import { formatStatusLabel } from "@/shared/lib/status-variants";
import { LoanItemStatus, type PlateLoan, type PlateLoanItem } from "../hooks/use-plate-loans";
import type { StorageLocation } from "../types";
import type { PlateStatus, RegisteredPlate } from "../types/plates";
import { isOverdue } from "./loan-summary";
import { storageFullPath, storagePath } from "./storage-path";

export type Whereabouts =
  | { kind: "custody"; loan: PlateLoan; item: PlateLoanItem; overdue: boolean }
  | { kind: "terminal"; status: "depleted" | "disposed" }
  | { kind: "location"; path: string; heroPath: string; fullPath: string }
  | { kind: "status"; status: PlateStatus };

/** Where a plate is, one answer: on loan > depleted/disposed > storage location > status. */
export function plateWhereabouts(
  plate: RegisteredPlate,
  custody: { loan: PlateLoan; item: PlateLoanItem } | undefined,
  locations: StorageLocation[] | undefined,
): Whereabouts {
  if (custody) {
    return {
      kind: "custody",
      loan: custody.loan,
      item: custody.item,
      overdue: isOverdue(custody.loan),
    };
  }
  if (plate.status === "depleted" || plate.status === "disposed") {
    return { kind: "terminal", status: plate.status };
  }
  const path = storagePath(locations, plate.storage_location_id);
  if (path) {
    return {
      kind: "location",
      path,
      // Spec §9: the plate page hero shows the last three levels.
      heroPath: storagePath(locations, plate.storage_location_id, 3),
      fullPath: storageFullPath(locations, plate.storage_location_id),
    };
  }
  return { kind: "status", status: plate.status };
}

export type WhereTone = "overdue" | "loan" | "muted" | "normal";

/** One-line text for the plate list's Where column. */
export function whereText(
  w: Whereabouts,
  requesterName: (id: string) => string,
): { text: string; tone: WhereTone; title?: string } {
  switch (w.kind) {
    case "custody": {
      const due = w.item.status === LoanItemStatus.checked_out ? formatDue(w.loan.due_date) : null;
      const phrase = due ? due.label : formatStatusLabel(w.item.status).toLowerCase();
      return {
        text: `${requesterName(w.loan.requested_by)} · ${phrase}`,
        tone: w.overdue ? "overdue" : "loan",
        title: w.loan.due_date ? `Due ${formatDate(w.loan.due_date)}` : undefined,
      };
    }
    case "terminal":
      return { text: formatStatusLabel(w.status), tone: "muted" };
    case "location":
      return { text: w.path, tone: "normal", title: w.fullPath };
    case "status":
      return { text: formatStatusLabel(w.status), tone: "muted" };
  }
}

export type PlateChipKey = "on_loan" | "overdue" | "depleted";
export const PLATE_CHIP_ORDER: PlateChipKey[] = ["on_loan", "overdue", "depleted"];
export const PLATE_CHIP_LABELS: Record<PlateChipKey, string> = {
  on_loan: "On loan",
  overdue: "Overdue",
  depleted: "Depleted",
};

export function plateChipKeys(plate: RegisteredPlate, w: Whereabouts): Set<PlateChipKey> {
  const keys = new Set<PlateChipKey>();
  if (w.kind === "custody") {
    keys.add("on_loan");
    if (w.overdue) keys.add("overdue");
  }
  if (plate.status === "depleted") keys.add("depleted");
  return keys;
}
