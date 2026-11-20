"use client";

import { PageHeader } from "@/shared/components/page-header";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useState } from "react";
import { useAuditOperations } from "../hooks/use-audit";
import { AuditTimelineView } from "./audit-timeline";

// ─── Filter options ──────────────────────────────────────────────────────────

const ENTITY_TYPE_OPTIONS = [
  { value: "_all", label: "All record types" },
  { value: "molecule", label: "Molecule" },
  { value: "batch", label: "Batch" },
  { value: "sample", label: "Sample" },
  { value: "protocol", label: "Protocol" },
  { value: "run", label: "Run" },
  { value: "RegisteredPlate", label: "Plate" },
  { value: "PlateGroup", label: "Plate Group" },
  { value: "PlateLoan", label: "Plate Loan" },
  { value: "organization", label: "Organization" },
  { value: "vocabulary", label: "Vocabulary" },
  { value: "settings", label: "Settings" },
] as const;

const LIMIT_OPTIONS = [
  { value: "25", label: "25" },
  { value: "50", label: "50" },
  { value: "100", label: "100" },
  { value: "200", label: "200" },
] as const;

// ─── Component ───────────────────────────────────────────────────────────────

export function AuditList() {
  const [entityType, setEntityType] = useState("_all");
  const [limit, setLimit] = useState("50");

  const filters = {
    entity_type: entityType === "_all" ? undefined : entityType,
    limit: Number(limit),
  };

  const { data, isLoading } = useAuditOperations(filters);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit Log"
        subtitle="Complete history of operations across the workspace."
      />

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select value={entityType} onValueChange={setEntityType}>
          <SelectTrigger aria-label="Record type" className="w-[180px]">
            <SelectValue placeholder="Record type" />
          </SelectTrigger>
          <SelectContent>
            {ENTITY_TYPE_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <span id="audit-limit-label" className="text-sm">
          Maximum entries to show
        </span>
        <Select value={limit} onValueChange={setLimit}>
          <SelectTrigger aria-labelledby="audit-limit-label" className="w-[100px]">
            <SelectValue placeholder="Maximum entries to show" />
          </SelectTrigger>
          <SelectContent>
            {LIMIT_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {data && !isLoading && (
          <span className="text-xs text-muted-foreground ml-auto">
            Showing {data.length} operation{data.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Timeline */}
      <AuditTimelineView operations={data} isLoading={isLoading} filtered={entityType !== "_all"} />
    </div>
  );
}
