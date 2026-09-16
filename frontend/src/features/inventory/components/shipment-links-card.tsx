"use client";

import { OrgName } from "@/shared/components/entity-name";
import { StatusBadge } from "@/shared/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { formatDate } from "@/shared/lib/format-date";
import Link from "next/link";
import { SHIPMENT_STATUS_LABELS, type ShipmentLink, type ShipmentStatus } from "../types/shipment";

interface ShipmentLinksCardProps {
  title: string;
  rows: ShipmentLink[] | undefined;
  isLoading?: boolean;
  emptyText: string;
}

/** The shipments a plate, a sample or a loan appeared in — one card for all three pages.
 * Row: `→ WuXi · In Transit · FedEx 7489 · shipped Sep 1, 2026 [· 5 mg]`, linking to the shipment. */
export function ShipmentLinksCard({ title, rows, isLoading, emptyText }: ShipmentLinksCardProps) {
  return (
    <Card data-testid="shipment-links">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows && rows.length > 0 ? (
          <ul className="divide-y rounded-md border">
            {rows.map((r) => (
              <li key={r.shipment_id}>
                <Link
                  href={`/inventory/shipments/${r.shipment_id}`}
                  className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm hover:bg-accent"
                >
                  <span className="font-medium">
                    {r.direction === "inbound" ? "←" : "→"} <OrgName id={r.destination_org_id} />
                  </span>
                  <StatusBadge
                    status={r.status}
                    label={SHIPMENT_STATUS_LABELS[r.status as ShipmentStatus] ?? r.status}
                  />
                  {r.carrier || r.tracking_number ? (
                    <span className="font-mono text-xs text-muted-foreground">
                      {[r.carrier, r.tracking_number].filter(Boolean).join(" ")}
                    </span>
                  ) : null}
                  <span className="text-muted-foreground">
                    {r.shipping_date ? "shipped" : "created"}{" "}
                    {formatDate(r.shipping_date ?? r.created_at)}
                  </span>
                  {r.amount_value != null ? (
                    <span className="ml-auto text-muted-foreground">
                      {r.amount_value} {r.amount_unit}
                    </span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{isLoading ? "…" : emptyText}</p>
        )}
      </CardContent>
    </Card>
  );
}
