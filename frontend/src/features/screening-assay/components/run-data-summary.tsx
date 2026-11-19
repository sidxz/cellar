"use client";

import { Card, CardContent } from "@/shared/components/ui/card";
import type { SpreadResponse } from "@/shared/lib/api/model";
import { Fragment } from "react";
import { usePlateMap } from "../hooks/use-plate-setup";
import { useProtocolPlateQcAverages } from "../hooks/use-protocol-stats";
import { type PlateLayerQc, readPlateLayerQc } from "../lib/qc-metrics";
import {
  type Protocol,
  READOUT_NORMALIZATION_LABELS,
  type ReadoutNormalization,
  type Run,
} from "../types";

const ROLE_LABEL: Record<string, string> = {
  positive_control: "Positive control",
  reference: "Reference",
};

/** 3 significant digits; float noise around zero (a normalized control mean) reads 0. */
const fmt = (v: number) => (Math.abs(v) < 1e-9 ? "0" : String(Number(v.toPrecision(3))));

const meanSd = (mean: number | undefined, sd: number | null | undefined, n: number | undefined) =>
  mean == null ? "—" : `${fmt(mean)}${sd != null ? ` ± ${fmt(sd)}` : ""} (${n ?? "?"})`;

/** Protocol averages: "0.91 ± 0.01 (2 plates)". */
const spread = (s: SpreadResponse | null | undefined, digits?: number, unit = "") => {
  if (!s) return "—";
  const f = (v: number) => (digits === undefined ? fmt(v) : v.toFixed(digits));
  const plates = `${s.n} plate${s.n === 1 ? "" : "s"}`;
  return `${f(s.mean)}${s.sd != null ? ` ± ${f(s.sd)}` : ""}${unit} (${plates})`;
};

interface Group {
  readoutId: string;
  layer: string;
  title: string;
  /** "role|molecule|label" of each control-compound potency column. */
  fits: string[];
}

/** One potency column per control compound and intercept. */
const fitKey = (f: { role: string; molecule_id?: string | null; label: string }) =>
  `${f.role}|${f.molecule_id ?? ""}|${f.label}`;

/** The run's plate QC like the platform's Data Summary: one row per plate, per readout x
 * layer its Z′ and each control's mean ± SD (n), and each control compound's potency; a
 * last row of protocol averages (mean ± SD over the protocol's plates). Nothing for a
 * run computed before per-layer plate QC existed. */
export function RunDataSummary({ run, protocol }: { run: Run; protocol: Protocol | undefined }) {
  const { data: plateMap } = usePlateMap(run.id);
  const { data: averages } = useProtocolPlateQcAverages(run.protocol_id);
  const perPlate = readPlateLayerQc(run.qc_metrics);
  const plateIds = Object.keys(perPlate);
  if (plateIds.length === 0) return null;

  const doseUnit = plateMap?.dose_unit ? ` ${plateMap.dose_unit}` : "";
  const plateNumber = new Map(plateMap?.plates.map((p) => [p.plate_id, p.plate_number]) ?? []);
  const compoundName = new Map(
    plateMap?.plates.flatMap((p) =>
      (p.wells ?? []).map((w) => [w.molecule_id, w.registration_number] as const),
    ) ?? [],
  );
  plateIds.sort((a, b) => (plateNumber.get(a) ?? 0) - (plateNumber.get(b) ?? 0));
  const averageOf = new Map(
    (averages?.averages ?? []).map((a) => [`${a.readout_definition_id}:${a.layer}`, a]),
  );

  // Groups: readouts in protocol order, raw before its normalizations.
  const defs = [...(protocol?.readout_definitions ?? [])].sort(
    (a, b) => a.display_order - b.display_order,
  );
  const order = new Map(defs.map((d, i) => [d.id, i]));
  const keys = new Map<string, Set<string>>();
  for (const pid of plateIds) {
    for (const [rd, layers] of Object.entries(perPlate[pid] ?? {})) {
      for (const [layer, qc] of Object.entries(layers ?? {})) {
        const fits = keys.get(`${rd}:${layer}`) ?? new Set<string>();
        for (const f of qc?.control_fits ?? []) fits.add(fitKey(f));
        keys.set(`${rd}:${layer}`, fits);
      }
    }
  }
  const groups: Group[] = [...keys]
    .map(([key, fits]) => {
      const [readoutId, layer] = key.split(":");
      for (const f of averageOf.get(key)?.control_fits ?? []) fits.add(fitKey(f));
      const def = defs.find((d) => d.id === readoutId);
      const name = def?.name ?? "Readout";
      const title =
        layer === "raw"
          ? `${name}${def?.unit ? ` (${def.unit})` : ""}`
          : `${name} · ${READOUT_NORMALIZATION_LABELS[layer as ReadoutNormalization] ?? layer}`;
      return { readoutId, layer, title, fits: [...fits].sort() };
    })
    .sort(
      (a, b) =>
        (order.get(a.readoutId) ?? 99) - (order.get(b.readoutId) ?? 99) ||
        Number(a.layer !== "raw") - Number(b.layer !== "raw") ||
        a.layer.localeCompare(b.layer),
    );

  const fitHeader = (fit: string) => {
    const [role, molecule, label] = fit.split("|");
    const name = compoundName.get(molecule);
    return `${ROLE_LABEL[role] ?? role} ${label}${name ? ` · ${name}` : ""}`;
  };
  const plateCells = (g: Group, qc: PlateLayerQc | undefined) => [
    qc?.z_prime != null ? qc.z_prime.toFixed(2) : "—",
    meanSd(qc?.pos_mean, qc?.pos_sd, qc?.pos_n),
    meanSd(qc?.neg_mean, qc?.neg_sd, qc?.neg_n),
    ...g.fits.map((fit) => {
      const values = (qc?.control_fits ?? [])
        .filter((f) => fitKey(f) === fit)
        .map((f) =>
          f.value != null
            ? `${fmt(f.value)}${doseUnit}`
            : f.curve_class === "inactive"
              ? "inactive"
              : f.curve_class === "active_all_doses"
                ? "active at all doses"
                : "—",
        );
      return values.length > 0 ? values.join(", ") : "—";
    }),
  ];
  const averageCells = (g: Group) => {
    const a = averageOf.get(`${g.readoutId}:${g.layer}`);
    return [
      spread(a?.z_prime, 2),
      spread(a?.pos_mean),
      spread(a?.neg_mean),
      ...g.fits.map((fit) =>
        spread(a?.control_fits?.find((f) => fitKey(f) === fit)?.value, undefined, doseUnit),
      ),
    ];
  };

  const cell = "whitespace-nowrap px-3 py-1.5 text-right text-sm tabular-nums";
  return (
    <Card>
      <CardContent className="space-y-3 p-4 sm:p-5">
        <h2 className="text-sm font-medium">Data summary</h2>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/30 text-xs text-muted-foreground">
              <tr>
                <th rowSpan={2} className="px-3 py-2 text-left font-medium">
                  Plate
                </th>
                {groups.map((g) => (
                  <th
                    key={`${g.readoutId}:${g.layer}`}
                    colSpan={3 + g.fits.length}
                    className="border-l px-3 py-1.5 text-center font-medium text-foreground"
                  >
                    {g.title}
                  </th>
                ))}
              </tr>
              <tr className="border-b">
                {groups.map((g) => (
                  <Fragment key={`${g.readoutId}:${g.layer}`}>
                    <th className="border-l px-3 py-1.5 text-right font-medium">Z′</th>
                    <th className="px-3 py-1.5 text-right font-medium">Positive control</th>
                    <th className="px-3 py-1.5 text-right font-medium">Negative control</th>
                    {g.fits.map((fit) => (
                      <th key={fit} className="px-3 py-1.5 text-right font-medium">
                        {fitHeader(fit)}
                      </th>
                    ))}
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {plateIds.map((pid) => (
                <tr key={pid} className="border-b">
                  <th scope="row" className="px-3 py-1.5 text-left text-sm font-medium">
                    Plate {plateNumber.get(pid) ?? "?"}
                  </th>
                  {groups.map((g) =>
                    plateCells(g, perPlate[pid]?.[g.readoutId]?.[g.layer]).map((text, i) => (
                      <td
                        key={`${g.readoutId}:${g.layer}:${i}`}
                        className={i === 0 ? `${cell} border-l` : cell}
                      >
                        {text}
                      </td>
                    )),
                  )}
                </tr>
              ))}
              <tr className="bg-muted/20">
                <th scope="row" className="px-3 py-1.5 text-left text-sm font-medium">
                  Protocol averages
                  <span className="block text-xs font-normal text-muted-foreground">
                    all runs except rejected
                  </span>
                </th>
                {groups.map((g) =>
                  averageCells(g).map((text, i) => (
                    <td
                      key={`${g.readoutId}:${g.layer}:${i}`}
                      className={i === 0 ? `${cell} border-l` : cell}
                    >
                      {text}
                    </td>
                  )),
                )}
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
