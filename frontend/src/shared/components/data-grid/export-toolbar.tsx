"use client";

import { type RefObject, useCallback } from "react";
import type { AgGridReact } from "ag-grid-react";
import { Download } from "lucide-react";
import * as XLSX from "xlsx";

import { Button } from "@/shared/components/ui/button";

interface ExportToolbarProps {
  gridRef: RefObject<AgGridReact | null>;
  filename: string;
}

export function ExportToolbar({ gridRef, filename }: ExportToolbarProps) {
  const handleCsvExport = useCallback(() => {
    gridRef.current?.api?.exportDataAsCsv({ fileName: `${filename}.csv` });
  }, [gridRef, filename]);

  const handleExcelExport = useCallback(() => {
    const api = gridRef.current?.api;
    if (!api) return;

    // Extract visible column headers
    const columns = api.getAllDisplayedColumns();
    const headers = columns.map((col) => {
      const colDef = col.getColDef();
      return (colDef.headerName ?? colDef.field ?? col.getColId()) as string;
    });
    const fields = columns.map((col) => col.getColDef().field ?? col.getColId());

    // Extract filtered/sorted rows using node data
    const rows: unknown[][] = [];
    api.forEachNodeAfterFilterAndSort((node) => {
      if (!node.data) return;
      const data = node.data as Record<string, unknown>;
      const row = fields.map((field) => {
        const value = data[field];
        if (value !== null && value !== undefined && typeof value === "object") {
          return JSON.stringify(value);
        }
        return value ?? "";
      });
      rows.push(row);
    });

    const worksheet = XLSX.utils.aoa_to_sheet([headers, ...rows]);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Data");
    XLSX.writeFile(workbook, `${filename}.xlsx`);
  }, [gridRef, filename]);

  return (
    <div className="flex gap-2">
      <Button variant="outline" size="sm" onClick={handleCsvExport}>
        <Download className="h-4 w-4" />
        CSV
      </Button>
      <Button variant="outline" size="sm" onClick={handleExcelExport}>
        <Download className="h-4 w-4" />
        Excel
      </Button>
    </div>
  );
}
