"use client";
import { ChevronDown, Download, Loader2 } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { ExportJobToast } from "./export-job-toast";
import type { ExportFormat, ExportRequest } from "./types";
import { useExport } from "./use-export";

const ITEMS: { format: ExportFormat; label: string; extension: string }[] = [
  { format: "xlsx", label: "Excel", extension: ".xlsx" },
  { format: "csv", label: "CSV", extension: ".csv" },
  { format: "sdf", label: "SDF", extension: ".sdf" },
  { format: "pdf", label: "PDF", extension: ".pdf" },
];

interface Props {
  buildRequest: (format: ExportFormat) => ExportRequest | null;
}

export function ExportToolbar({ buildRequest }: Props) {
  const exp = useExport();

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" disabled={exp.isPending}>
            {exp.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            Export
            <ChevronDown className="ml-1 size-3 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[10rem]">
          {ITEMS.map((it) => (
            <DropdownMenuItem
              key={it.format}
              onSelect={() => {
                const req = buildRequest(it.format);
                if (req) void exp.start(req);
              }}
            >
              <span>{it.label}</span>
              <span className="ml-auto text-[11px] tracking-wide text-muted-foreground">
                {it.extension}
              </span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <ExportJobToast
        job={exp.job}
        error={exp.error}
        onCancel={exp.cancel}
        onDownload={exp.download}
        onDismiss={exp.reset}
      />
    </>
  );
}
