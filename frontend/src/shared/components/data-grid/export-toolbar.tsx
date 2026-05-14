"use client";

import type { AgGridReact } from "ag-grid-react";
import ExcelJS from "exceljs";
import { ChevronDown, Download, Loader2 } from "lucide-react";
import { type RefObject, useCallback, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";

/**
 * After the main data worksheet is created, the enhancer can add
 * sparkline images, extra sheets, styling, etc.
 */
export type ExcelEnhancer = (
  workbook: ExcelJS.Workbook,
  worksheet: ExcelJS.Worksheet,
  /** Row data extracted from the grid (same order as worksheet rows) */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  rows: any[],
) => Promise<void>;

/**
 * Extra dropdown item appended after Excel + CSV — e.g. a feature-specific
 * format like SDF (structures-only) on the search results, or a JSON
 * snapshot on a config screen. The toolbar handles the menu chrome and
 * the loading spinner; the consumer's `onSelect` does the actual work.
 */
export interface ExtraExportItem {
  label: string;
  /** Filename extension hint rendered on the right of the dropdown row
   *  (e.g. ".sdf" — no leading dot is enforced; the toolbar passes
   *  through whatever the caller provides for parity with .xlsx/.csv). */
  extension: string;
  onSelect: () => void | Promise<void>;
}

interface ExportToolbarProps {
  gridRef: RefObject<AgGridReact | null>;
  filename: string;
  /** Optional enhancer for Excel exports — adds images, extra sheets, etc. */
  excelEnhancer?: ExcelEnhancer;
  /** Additional dropdown items rendered after Excel + CSV — caller owns
   *  the export action (e.g. backend SDF download). */
  extraItems?: ExtraExportItem[];
}

export function ExportToolbar({
  gridRef,
  filename,
  excelEnhancer,
  extraItems,
}: ExportToolbarProps) {
  const [exporting, setExporting] = useState(false);

  const handleCsvExport = useCallback(() => {
    gridRef.current?.api?.exportDataAsCsv({ fileName: `${filename}.csv` });
  }, [gridRef, filename]);

  const handleExcelExport = useCallback(async () => {
    const api = gridRef.current?.api;
    if (!api) return;

    setExporting(true);
    try {
      const columns = api.getAllDisplayedColumns();
      const headers = columns.map((col) => {
        const colDef = col.getColDef();
        return (colDef.headerName ?? colDef.field ?? col.getColId()) as string;
      });

      // Extract rows — keep both display values and raw row data
      const displayRows: unknown[][] = [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const rawRows: any[] = [];
      api.forEachNodeAfterFilterAndSort((node) => {
        if (!node.data) return;
        rawRows.push(node.data);
        const row = columns.map((col) => {
          const value = api.getCellValue({ rowNode: node, colKey: col });
          if (value !== null && value !== undefined && typeof value === "object") {
            return JSON.stringify(value);
          }
          return value ?? "";
        });
        displayRows.push(row);
      });

      // Build workbook with exceljs
      const workbook = new ExcelJS.Workbook();
      const worksheet = workbook.addWorksheet("Data");

      // Header row — simple bold, no background color
      const headerRow = worksheet.addRow(headers);
      headerRow.font = { bold: true };

      // Data rows
      for (const row of displayRows) {
        worksheet.addRow(row);
      }

      // Auto-width columns. Single pass: O(rows × columns) only walks each
      // cell once total, instead of once per (row, column) pair.
      const maxLens = headers.map((h) => String(h ?? "").length);
      for (const row of displayRows) {
        for (let i = 0; i < maxLens.length; i++) {
          const cellLen = String(row[i] ?? "").length;
          if (cellLen > maxLens[i]) maxLens[i] = cellLen;
        }
      }
      worksheet.columns.forEach((col, i) => {
        col.width = Math.min(Math.max(maxLens[i] + 2, 10), 40);
      });

      // Call enhancer if provided (adds images, extra sheets, etc.)
      if (excelEnhancer) {
        await excelEnhancer(workbook, worksheet, rawRows);
      }

      // Write and download
      const buffer = await workbook.xlsx.writeBuffer();
      const blob = new Blob([buffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [gridRef, filename, excelEnhancer]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={exporting}>
          {exporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Export
          <ChevronDown className="ml-1 size-3 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[10rem]">
        <DropdownMenuItem onSelect={() => void handleExcelExport()}>
          <span>Excel</span>
          <span className="ml-auto text-[11px] tracking-wide text-muted-foreground">.xlsx</span>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => handleCsvExport()}>
          <span>CSV</span>
          <span className="ml-auto text-[11px] tracking-wide text-muted-foreground">.csv</span>
        </DropdownMenuItem>
        {extraItems?.map((item) => (
          <DropdownMenuItem
            key={item.label}
            onSelect={() => {
              const result = item.onSelect();
              if (result instanceof Promise) {
                setExporting(true);
                result.finally(() => setExporting(false));
              }
            }}
          >
            <span>{item.label}</span>
            <span className="ml-auto text-[11px] tracking-wide text-muted-foreground">
              {item.extension}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
