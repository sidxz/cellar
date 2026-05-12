"use client";

import type { CampaignResultResponse, CampaignResponse } from "../../types";

interface RowDetailRendererProps {
  // AG-Grid passes the row data via `data`.
  data: { result: CampaignResultResponse; campaign: CampaignResponse };
}

export function RowDetailRenderer({ data }: RowDetailRendererProps) {
  const { result, campaign } = data;
  const channelsById = new Map(
    (campaign.channels ?? []).map((c) => [c.id, c] as const),
  );

  return (
    <div className="border-t bg-muted/30 p-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Decision rationale
          </h3>
          <p className="whitespace-pre-wrap text-sm">
            {result.decision_reason || (
              <em className="text-muted-foreground">none</em>
            )}
          </p>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Notes
          </h3>
          <p className="whitespace-pre-wrap text-sm">
            {result.notes || (
              <em className="text-muted-foreground">none</em>
            )}
          </p>
        </section>
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Per-channel audit
          </h3>
          <table className="w-full text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="text-left">Channel</th>
                <th className="text-left">Value</th>
                <th className="text-left">[conc]</th>
                <th className="text-left">N</th>
                <th className="text-left">QC</th>
              </tr>
            </thead>
            <tbody>
              {(result.measurements ?? []).map((m) => (
                <tr key={m.id}>
                  <td>
                    {channelsById.get(m.channel_id)?.label ??
                      m.channel_id.slice(0, 8)}
                  </td>
                  <td>
                    {m.value ?? "—"} {m.unit}
                  </td>
                  <td>
                    {m.test_concentration_value ?? "—"}
                    {m.test_concentration_value != null &&
                    m.test_concentration_unit
                      ? ` ${m.test_concentration_unit}`
                      : ""}
                  </td>
                  <td>{m.replicate_count ?? "—"}</td>
                  <td>
                    {m.qc_pass == null ? "—" : m.qc_pass ? "pass" : "fail"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
      {(result.measurements ?? []).some((m) => m.is_manual_override) && (
        <section className="mt-4">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Override history
          </h3>
          <ul className="space-y-1 text-sm">
            {(result.measurements ?? [])
              .filter((m) => m.is_manual_override)
              .map((m) => (
                <li key={m.id}>
                  <strong>
                    {channelsById.get(m.channel_id)?.label ??
                      m.channel_id.slice(0, 8)}
                  </strong>
                  :{" "}
                  {m.value ?? "—"} {m.unit} —{" "}
                  <em>{m.override_reason ?? "no reason recorded"}</em>
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}
