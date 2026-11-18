/**
 * Display text for a column's description (spec §6.6). The label sentences are
 * built server-side; this only restates their parts for hover text.
 */

import { sameConcentration } from "@/features/screening-assay/lib/test-concentration";
import type { ConcentrationDTO } from "@/shared/lib/api/model";
import type { CampaignChannelResponse } from "../types";

/** "10 µM"; "not recorded" for the bucket with no known concentration. */
export function concentrationText(c: { value?: number | null; unit?: string | null }): string {
  return c.value == null ? "not recorded" : `${c.value} ${c.unit ?? ""}`.trim();
}

/** "1 compound", "20 compounds". */
export const compoundsText = (n: number) => `${n} ${n === 1 ? "compound" : "compounds"}`;

/** "10 µM and 50 µM"; "1 µM, 10 µM and 50 µM". */
export const listText = (items: string[]) =>
  new Intl.ListFormat("en-GB", { type: "conjunction" }).format(items);

// How the server reads a recorded dose (measurement_facts._TEXT); a bare number is µM.
const DOSE = /^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(\S*)\s*$/;

/** "1 run at 50 µM set aside": the runs a column reads that were recorded at
 *  another dose than the chosen one. A dose not recorded or not readable counts
 *  as neither; null when no run is set aside. */
export function setAsideText(
  recorded: (string | undefined)[],
  chosen: ConcentrationDTO,
): string | null {
  const other = recorded.filter((raw): raw is string => {
    const m = raw ? DOSE.exec(raw) : null;
    return (
      !!m &&
      !sameConcentration(
        { value: m[1] as string, unit: m[2] || "µM" },
        { value: String(chosen.value), unit: chosen.unit },
      )
    );
  });
  if (other.length === 0) return null;
  const runs = other.length === 1 ? "1 run" : `${other.length} runs`;
  return `${runs} at ${listText([...new Set(other)])} set aside`;
}

const DESIGN_TEXT: Record<string, string> = {
  concentration_series: "dose-response",
  reported: "reported value",
  not_recorded: "not recorded",
};

/** Header hover text: the full label, then one line per part. */
export function columnTooltip(channel: CampaignChannelResponse, protocolName?: string): string {
  const d = channel.description;
  if (!d) return protocolName ? `${channel.label}\nProtocol: ${protocolName}` : channel.label;
  const known = d.concentrations.filter((c) => c.value != null).map(concentrationText);
  const design =
    DESIGN_TEXT[d.design] ??
    (known.length > 1 ? `several (${known.join(", ")})` : (known[0] ?? "not recorded"));
  const { min, max, not_recorded } = d.replicates;
  const replicates =
    (min == null ? "not recorded" : min === max ? `${min}` : `${min}–${max}`) +
    (min != null && not_recorded > 0 ? ` (${not_recorded} not recorded)` : "");
  return [
    d.label,
    "",
    d.stage_name && `Stage: ${d.stage_name}`,
    `Readout: ${d.readout_label}`,
    protocolName && `Protocol: ${protocolName}`,
    `Concentration: ${design}`,
    channel.test_concentration && `Values at: ${concentrationText(channel.test_concentration)}`,
    d.design !== "concentration_series" && `Replicates: ${replicates}`,
    `Runs: ${d.run_count}`,
    `Rule: ${d.rule}`,
    d.basis.length > 0 && `Basis: ${d.basis.join(", ")}`,
  ]
    .filter((line) => line !== false && line != null)
    .join("\n");
}
