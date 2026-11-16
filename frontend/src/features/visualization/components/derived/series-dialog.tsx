"use client";

import { useScaffoldTree } from "@/features/sar-analysis/hooks/use-scaffold-tree";
import { buildCoreCandidates } from "@/features/sar-analysis/lib/sar-core-candidates";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { type DerivedSet, type SeriesMember, letters, seriesSet } from "../../lib/derived";
import type { Dataset } from "../../types";

const MAX_SERIES = 8;
const tile =
  "flex flex-col items-center gap-1 rounded-md border border-input p-1.5 text-xs hover:bg-muted disabled:pointer-events-none disabled:opacity-50";

/** An R-groups set as a series source: its core and how many compounds match it. */
function coreOf(set: DerivedSet) {
  if (set.spec.kind !== "rgroups") return null;
  const match = `chem:${set.spec.id}:match`;
  const n = [...set.byMolecule.values()].filter((v) => v[match] === "Matches").length;
  return {
    id: set.spec.id,
    smiles: set.spec.coreSmiles,
    label: `R-group core · ${set.spec.name} · ${n.toLocaleString()} match`,
  };
}

/** "Series…": named series from shared scaffolds (compounds containing them) or R-group cores
 * (compounds matching them), in priority order, with a live preview of the Series column. */
export function SeriesDialog({
  open,
  onOpenChange,
  ds,
  moleculeIds,
  rgroupSets,
  initial = [],
  onApply,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ds: Dataset;
  /** The compounds the series job runs over (its scaffold tree is the one shown here). */
  moleculeIds: string[];
  rgroupSets: DerivedSet[];
  initial?: SeriesMember[];
  onApply: (members: SeriesMember[]) => void;
}) {
  const { tree, isStarting, isPolling, error } = useScaffoldTree({ moleculeIds });
  const candidates = useMemo(() => (tree ? buildCoreCandidates(tree).candidates : []), [tree]);
  const cores = rgroupSets.flatMap((s) => coreOf(s) ?? []);
  const [members, setMembers] = useState<SeriesMember[]>(initial);
  const full = members.length >= MAX_SERIES;

  const add = (source: Omit<SeriesMember, "name">) => {
    const names = new Set(members.map((m) => m.name));
    let k = 1;
    while (names.has(`Series ${letters(k)}`)) k++;
    setMembers([...members, { name: `Series ${letters(k)}`, ...source }]);
  };
  const rename = (k: number, name: string) =>
    setMembers(members.map((m, j) => (j === k ? { ...m, name } : m)));

  const preview = useMemo(
    () =>
      members.length > 0 && (tree || !members.some((m) => m.scaffold))
        ? seriesSet({ id: "series", kind: "series", members }, ds, tree, rgroupSets)
        : null,
    [members, ds, tree, rgroupSets],
  );
  const names = members.map((m) => m.name.trim());
  // "Other" is the rest's name.
  const badName = names.some((n) => !n) || new Set([...names, "Other"]).size !== names.length + 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a series column</DialogTitle>
          <DialogDescription>
            Pick scaffolds or R-group cores. Each compound goes to the first series it belongs to;
            the rest are Other.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-start gap-2">
          {candidates.map((c) => (
            <button
              key={c.scaffoldSmiles}
              type="button"
              className={tile}
              aria-label={`Scaffold ${c.scaffoldSmiles} — in ${c.coverage} compounds`}
              title={c.scaffoldSmiles}
              disabled={full || members.some((m) => m.scaffold === c.scaffoldSmiles)}
              onClick={() => add({ scaffold: c.scaffoldSmiles })}
            >
              <StructureThumbnail smiles={c.scaffoldSmiles} size={56} />
              <span className="tabular-nums text-muted-foreground">
                {c.coverage.toLocaleString()} compounds
              </span>
            </button>
          ))}
          {cores.map((c) => (
            <button
              key={c.id}
              type="button"
              className={tile}
              aria-label={c.label}
              disabled={full || members.some((m) => m.rgroupsId === c.id)}
              onClick={() => add({ rgroupsId: c.id })}
            >
              <StructureThumbnail smiles={c.smiles} size={56} />
              {c.label}
            </button>
          ))}
        </div>
        {isStarting || isPolling ? (
          <p className="text-xs text-muted-foreground">Finding scaffolds…</p>
        ) : error ? (
          <p className="text-xs text-destructive">Could not load scaffolds.</p>
        ) : (
          tree &&
          candidates.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No scaffold is shared by 3 or more compounds. Add R-groups with a drawn core and use
              it here.
            </p>
          )
        )}

        {members.length > 0 && (
          <ol className="space-y-1.5">
            {members.map((m, k) => (
              <li key={m.scaffold ?? m.rgroupsId} className="flex items-center gap-2">
                <span className="w-4 text-right text-xs text-muted-foreground">{k + 1}</span>
                <StructureThumbnail
                  smiles={m.scaffold ?? cores.find((c) => c.id === m.rgroupsId)?.smiles ?? ""}
                  size={32}
                />
                <Input
                  aria-label={`Series ${k + 1} name`}
                  maxLength={60}
                  className="h-8 max-w-60"
                  value={m.name}
                  onChange={(e) => rename(k, e.target.value)}
                />
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  aria-label={`Remove ${m.name}`}
                  onClick={() => setMembers(members.filter((_, j) => j !== k))}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ol>
        )}
        <div className="space-y-0.5 text-sm">
          {full && <p className="text-muted-foreground">Up to {MAX_SERIES} series.</p>}
          {preview && <p className="text-muted-foreground">{preview.summary}</p>}
          {preview?.warning && <p className="text-warning">{preview.warning}</p>}
          {badName && <p className="text-warning">Give each series its own name.</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={members.length === 0 || badName}
            onClick={() => {
              onApply(members.map((m, k) => ({ ...m, name: names[k] })));
              onOpenChange(false);
            }}
          >
            Add series column
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
