"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";
import { Badge } from "@/shared/components/ui/badge";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { cn } from "@/shared/lib/utils";

export interface MoleculeCardProps {
  molecule: Molecule;
  selected: boolean;
  onSelectChange: (moleculeId: string, selected: boolean) => void;
  onOpen: (moleculeId: string) => void;
  /**
   * Number of distinct protocols this molecule has been tested in.
   * When > 0, a quiet grey "Tested in N protocols" line is rendered
   * below the property strip.  Omit or pass 0/undefined to hide it.
   */
  protocolCount?: number;
  className?: string;
}

function formatMW(mw: number | null | undefined): string {
  return typeof mw === "number" ? mw.toFixed(0) : "—";
}

function formatLogP(v: number | null | undefined): string {
  return typeof v === "number" ? v.toFixed(1) : "—";
}

/**
 * Derive a Ro5 pass/fail from `ro5_violations`.
 * 0 violations → pass (✓); any violations → fail (✗); null → not shown.
 */
function ro5Status(violations: number | null | undefined): boolean | null {
  if (violations === null || violations === undefined) return null;
  return violations === 0;
}

export function MoleculeCard({
  molecule,
  selected,
  onSelectChange,
  onOpen,
  protocolCount,
  className,
}: MoleculeCardProps) {
  const desc = molecule.descriptors;
  const mw = desc?.molecular_weight;
  const logp = desc?.logp;
  const ro5 = ro5Status(desc?.ro5_violations);
  const displayName = molecule.name ?? molecule.registration_number ?? molecule.id;

  return (
    <div
      className={cn(
        "group relative flex flex-col rounded-lg border bg-card shadow-sm transition-shadow hover:shadow-md",
        selected && "ring-2 ring-primary",
        className,
      )}
    >
      <div className="absolute right-2 top-2 z-10">
        <Checkbox
          checked={selected}
          onCheckedChange={(v) => onSelectChange(molecule.id, v === true)}
          aria-label={`Select ${displayName}`}
        />
      </div>
      <button
        type="button"
        onClick={() => onOpen(molecule.id)}
        aria-label={`open ${displayName} detail`}
        className="flex flex-1 flex-col text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
      >
        <div className="flex items-center justify-center bg-muted/30 p-3">
          <MoleculeThumbnail smiles={molecule.structure?.smiles ?? ""} size="md" />
        </div>
        <div className="flex flex-col gap-1 border-t p-3">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-mono text-xs text-muted-foreground">
              {molecule.registration_number ?? "—"}
            </span>
          </div>
          <div className="truncate text-sm font-medium" title={molecule.name ?? ""}>
            {molecule.name ?? "—"}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span>MW {formatMW(mw)}</span>
            <span>·</span>
            <span>cLogP {formatLogP(logp)}</span>
            {ro5 !== null && (
              <>
                <span>·</span>
                <Badge variant={ro5 ? "secondary" : "destructive"} className="h-4 px-1 text-[10px]">
                  {ro5 ? "Ro5 ✓" : "Ro5 ✗"}
                </Badge>
              </>
            )}
          </div>
          {typeof protocolCount === "number" && protocolCount > 0 && (
            <div className="text-xs text-muted-foreground">
              Tested in {protocolCount} protocol{protocolCount === 1 ? "" : "s"}
            </div>
          )}
        </div>
      </button>
    </div>
  );
}
