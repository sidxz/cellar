"use client";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useProtocol } from "@/features/screening-assay/hooks/use-protocols";

const STANDARD_TARGET_OPTIONS = [
  { value: "skip", label: "— Skip —" },
  { value: "plate_barcode", label: "Plate Barcode" },
  { value: "well_position", label: "Well Position" },
  { value: "molecule_identifier", label: "Molecule Identifier" },
  { value: "qualifier", label: "Qualifier" },
] as const;

interface ColumnMappingStepProps {
  headers: string[];
  previewRows: string[][];
  columnMappings: Record<string, string>;
  onMappingsChange: (mappings: Record<string, string>) => void;
  protocolId?: string;
}

export function ColumnMappingStep({
  headers,
  previewRows,
  columnMappings,
  onMappingsChange,
  protocolId,
}: ColumnMappingStepProps) {
  const { data: protocol } = useProtocol(protocolId || undefined);
  const readoutDefs = protocol?.readout_definitions ?? [];

  const firstRow = previewRows[0] ?? [];

  function handleChange(header: string, target: string) {
    onMappingsChange({ ...columnMappings, [header]: target });
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[200px]">File Column</TableHead>
            <TableHead className="w-[200px]">Sample Value</TableHead>
            <TableHead>Map To</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {headers.map((header, idx) => (
            <TableRow key={header}>
              <TableCell className="font-mono text-sm font-medium">
                {header}
              </TableCell>
              <TableCell className="font-mono text-sm text-muted-foreground truncate max-w-[200px]">
                {firstRow[idx] ?? "—"}
              </TableCell>
              <TableCell>
                <Select
                  value={columnMappings[header] ?? "skip"}
                  onValueChange={(val) => handleChange(header, val)}
                >
                  <SelectTrigger className="w-[260px]">
                    <SelectValue placeholder="Select target field" />
                  </SelectTrigger>
                  <SelectContent>
                    {STANDARD_TARGET_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}

                    {readoutDefs.length > 0 && (
                      <>
                        <SelectSeparator />
                        <SelectGroup>
                          <SelectLabel>Readout Definitions</SelectLabel>
                          {readoutDefs.map((rd) => (
                            <SelectItem key={rd.id} value={`readout:${rd.id}`}>
                              {rd.name}
                              {rd.unit ? ` (${rd.unit})` : ""}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </>
                    )}
                  </SelectContent>
                </Select>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
