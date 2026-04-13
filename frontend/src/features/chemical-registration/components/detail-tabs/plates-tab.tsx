"use client";

import Link from "next/link";
import { useMoleculePlates } from "@/features/inventory/hooks/use-plates";
import { plateTypeLabels, plateStatusLabels } from "@/features/inventory/types/plates";
import { Badge } from "@/shared/components/ui/badge";

interface PlatesTabProps {
  moleculeId: string;
}

export function PlatesTab({ moleculeId }: PlatesTabProps) {
  const { data: entries, isLoading } = useMoleculePlates(moleculeId);

  if (isLoading) {
    return <div className="py-8 text-center text-muted-foreground">Loading...</div>;
  }

  if (!entries || entries.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        No plates contain this compound
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-4 py-2 text-left font-medium">Barcode</th>
              <th className="px-4 py-2 text-left font-medium">Label</th>
              <th className="px-4 py-2 text-left font-medium">Well</th>
              <th className="px-4 py-2 text-left font-medium">Concentration</th>
              <th className="px-4 py-2 text-left font-medium">Type</th>
              <th className="px-4 py-2 text-left font-medium">Status</th>
              <th className="px-4 py-2 text-left font-medium">Location</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={`${entry.plate_id}-${entry.well_position}`} className="border-b last:border-0">
                <td className="px-4 py-2">
                  <Link
                    href={`/inventory/plates/${entry.plate_id}`}
                    className="font-mono text-primary hover:underline"
                  >
                    {entry.barcode}
                  </Link>
                </td>
                <td className="px-4 py-2">{entry.plate_label}</td>
                <td className="px-4 py-2 font-mono">{entry.well_position}</td>
                <td className="px-4 py-2">
                  {entry.concentration_value != null
                    ? `${entry.concentration_value} ${entry.concentration_unit ?? ""}`
                    : "—"}
                </td>
                <td className="px-4 py-2">
                  <Badge variant="outline">
                    {plateTypeLabels[entry.plate_type as keyof typeof plateTypeLabels] ?? entry.plate_type}
                  </Badge>
                </td>
                <td className="px-4 py-2">
                  <Badge variant="secondary">
                    {plateStatusLabels[entry.status as keyof typeof plateStatusLabels] ?? entry.status}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-muted-foreground">
                  {entry.storage_location_name ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
