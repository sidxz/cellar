"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { CompoundCurvesButton } from "@/features/screening-assay/components/compound-curves-dialog";
import type { Protocol } from "@/features/screening-assay/types";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { EntityLink } from "@/shared/components/entity-link";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { ListPlus, X } from "lucide-react";
import { useMemo } from "react";
import { selectivityRatio } from "../../lib/assay-evidence";
import { comparisonChannels } from "../../lib/comparison-channels";
import { compoundRef, curvesTarget } from "../../lib/curves-target";
import { AGGREGATION_LABELS, type AggregationMode } from "../../lib/use-aggregation-mode";
import type { ActivityValue } from "../../types";
import { AssayResult } from "./assay-result";
import { ComparisonCompoundPicker } from "./comparison-compound-picker";

type ComparisonMolecule = Molecule & { activity?: Record<string, ActivityValue> };
const PROPERTIES = [
  ["molecular_weight", "MW (g/mol)", 1],
  ["logp", "LogP", 2],
  ["tpsa", "TPSA (Å²)", 1],
  ["hbd", "H-bond donors", 0],
  ["hba", "H-bond acceptors", 0],
  ["rotatable_bonds", "Rotatable bonds", 0],
] as const;

export function CompoundComparison({
  molecules,
  protocolColumns,
  protocols,
  mode,
  onClose,
  open = true,
  availableMolecules,
  onMoleculesChange,
  endpointPair,
  onEndpointPairChange,
  onSaveShortlist,
  onLoadMore,
  loading,
}: {
  molecules: ComparisonMolecule[];
  protocolColumns: string[];
  protocols: Protocol[];
  mode: AggregationMode;
  onClose: () => void;
  open?: boolean;
  availableMolecules: ComparisonMolecule[];
  onMoleculesChange: (ids: string[]) => void;
  endpointPair: { targetId: string; counterId: string };
  onEndpointPairChange: (pair: { targetId: string; counterId: string }) => void;
  onSaveShortlist: () => void;
  onLoadMore?: () => void;
  loading?: boolean;
}) {
  const channels = useMemo(
    () => comparisonChannels(protocolColumns, protocols),
    [protocolColumns, protocols],
  );
  const potency = channels.filter((c) => c.doseResponse);
  const { targetId, counterId } = endpointPair;
  const ids = molecules.map((mol) => mol.id);
  const candidates = availableMolecules.filter((mol) => !ids.includes(mol.id));
  const target = potency.find((c) => c.id === targetId);
  const counter = potency.find((c) => c.id === counterId);
  const pairIssue =
    !target || !counter
      ? "Choose a target and counter assay above"
      : target.id === counter.id
        ? "Choose two different assay endpoints"
        : !target.endpointType || target.endpointType !== counter.endpointType
          ? "Choose matching endpoint types and levels"
          : null;
  const thClass =
    "sticky left-0 z-10 w-36 min-w-36 sm:w-52 sm:min-w-52 border-b bg-background px-4 py-3 text-left text-sm font-medium";
  const tdClass = "min-w-60 border-b px-4 py-3 align-top text-sm";
  return (
    <Dialog open={open} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[90dvh] w-[calc(100%-2rem)] flex-col gap-4 overflow-hidden sm:max-w-[1200px]">
        <DialogHeader className="pr-6">
          <DialogTitle>
            {molecules.length
              ? `Compare ${molecules.length} compound${molecules.length === 1 ? "" : "s"}`
              : "Compare compounds"}
          </DialogTitle>
          <DialogDescription>
            Current search results · {AGGREGATION_LABELS[mode]}. Assay values retain the executed
            search’s run scope. Open a value to trace its evidence.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-2">
          <ComparisonCompoundPicker
            candidates={candidates}
            label="Add compound"
            disabled={molecules.length >= 4}
            onPick={(id) => onMoleculesChange([...ids, id])}
            onLoadMore={onLoadMore}
            loading={loading}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={molecules.length === 0}
            onClick={onSaveShortlist}
          >
            <ListPlus className="mr-1.5 h-4 w-4" />
            Save shortlist ({molecules.length})
          </Button>
          <span className="text-xs text-muted-foreground">
            {molecules.length < 2
              ? "Add at least two compounds to compare."
              : `${molecules.length} of 4 comparison slots`}
          </span>
        </div>
        {potency.length >= 2 ? (
          <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
            <p className="text-sm font-medium">Selectivity · counter potency / target potency</p>
            <div className="flex flex-wrap gap-3">
              {(["Target", "Counter"] as const).map((label) => (
                <label
                  key={label}
                  className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-muted-foreground"
                >
                  {label} assay
                  <select
                    className="h-9 w-full min-w-0 rounded-md border bg-background px-2 text-sm text-foreground"
                    value={label === "Target" ? (target?.id ?? "") : (counter?.id ?? "")}
                    onChange={(e) =>
                      onEndpointPairChange({
                        ...endpointPair,
                        [label === "Target" ? "targetId" : "counterId"]: e.target.value,
                      })
                    }
                  >
                    <option value="">Choose an endpoint…</option>
                    {potency.map((channel) => (
                      <option key={channel.id} value={channel.id}>
                        {channel.protocolName} · {channel.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              A ratio above 1 means a lower target potency value. Units are converted before
              calculation; assay conditions and run dates may differ.
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            To compare selectivity, add target and counter dose-response endpoints using Columns
            &amp; display.
          </p>
        )}
        <section
          className="min-h-0 overflow-auto rounded-lg border"
          // biome-ignore lint/a11y/noNoninteractiveTabindex: Keyboard users need to scroll the comparison table.
          tabIndex={0}
          aria-label="Compound comparison table"
        >
          <table className="w-full border-separate border-spacing-0">
            <thead className="sticky top-0 z-20 bg-background">
              <tr>
                <th className={thClass} scope="col">
                  Compound
                </th>
                {molecules.map((mol) => (
                  <th
                    key={mol.id}
                    scope="col"
                    className={`${tdClass} bg-background text-left font-normal`}
                  >
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <ComparisonCompoundPicker
                        candidates={candidates}
                        label={`Replace ${mol.registration_number ?? mol.name ?? "compound"}`}
                        onPick={(id) =>
                          onMoleculesChange(ids.map((oldId) => (oldId === mol.id ? id : oldId)))
                        }
                        onLoadMore={onLoadMore}
                        loading={loading}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0"
                        aria-label={`Remove ${mol.registration_number ?? mol.name ?? "compound"} from comparison`}
                        onClick={() => onMoleculesChange(ids.filter((id) => id !== mol.id))}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                    <div className="flex items-center gap-3">
                      {mol.structure?.smiles && (
                        <StructureThumbnail smiles={mol.structure.smiles} size={88} />
                      )}
                      <div className="min-w-0">
                        <EntityLink
                          type="compound"
                          id={mol.id}
                          label={mol.registration_number ?? "Open compound"}
                          className="text-xs"
                        />
                        <p className="mt-1 break-words text-sm">{mol.name || "Unnamed"}</p>
                      </div>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {channels.map((channel, index) => (
                <tr key={channel.id}>
                  <th scope="row" className={thClass}>
                    <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                      {channel.protocolName}
                      {/* Once per protocol, on its first row. */}
                      {channels.findIndex((c) => c.protocolId === channel.protocolId) === index && (
                        <CompoundCurvesButton
                          className="text-foreground"
                          target={curvesTarget(
                            protocols.find((p) => p.id === channel.protocolId),
                            molecules.map(compoundRef),
                          )}
                        />
                      )}
                    </span>
                    {channel.label}
                    {channel.unit ? ` (${channel.unit})` : ""}
                  </th>
                  {molecules.map((mol) => {
                    const av = mol.activity?.[channel.activityKey];
                    return (
                      <td key={mol.id} className={tdClass}>
                        <AssayResult av={av} channel={channel} mode={mode} />
                      </td>
                    );
                  })}
                </tr>
              ))}
              {potency.length >= 2 && (
                <tr>
                  <th scope="row" className={thClass}>
                    Selectivity (fold)
                  </th>
                  {molecules.map((mol) => {
                    const ratio =
                      pairIssue || !target || !counter
                        ? { value: null, reason: pairIssue ?? "Choose endpoints" }
                        : selectivityRatio(
                            {
                              av: mol.activity?.[target.activityKey],
                              spec: target.spec,
                              isPrimary: target.isPrimary,
                            },
                            {
                              av: mol.activity?.[counter.activityKey],
                              spec: counter.spec,
                              isPrimary: counter.isPrimary,
                            },
                            mode,
                          );
                    return (
                      <td key={mol.id} className={tdClass}>
                        <p className="font-mono">
                          {ratio.value == null ? "—" : `${ratio.value.toPrecision(3)}×`}
                        </p>
                        {ratio.value == null && (
                          <p className="mt-1 text-xs text-muted-foreground">{ratio.reason}</p>
                        )}
                      </td>
                    );
                  })}
                </tr>
              )}
              {PROPERTIES.map(([key, label, digits]) => (
                <tr key={key}>
                  <th scope="row" className={thClass}>
                    {label}
                  </th>
                  {molecules.map((mol) => (
                    <td key={mol.id} className={`${tdClass} font-mono tabular-nums`}>
                      {mol.descriptors?.[key]?.toFixed(digits) ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <p className="text-xs text-muted-foreground">
          — = no available value. ND = not determined. Qualified endpoints and missing units are not
          used for selectivity ratios.
        </p>
      </DialogContent>
    </Dialog>
  );
}
