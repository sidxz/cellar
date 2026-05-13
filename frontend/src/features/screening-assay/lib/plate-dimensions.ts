import type { PlateFormat } from "../types";

const DIMENSIONS: Record<PlateFormat, { rows: number; cols: number }> = {
  "6": { rows: 2, cols: 3 },
  "12": { rows: 3, cols: 4 },
  "24": { rows: 4, cols: 6 },
  "48": { rows: 6, cols: 8 },
  "96": { rows: 8, cols: 12 },
  "384": { rows: 16, cols: 24 },
  "1536": { rows: 32, cols: 48 },
};

const CELL_SIZE_PX: Record<PlateFormat, number> = {
  "6": 28,
  "12": 28,
  "24": 28,
  "48": 28,
  "96": 28,
  "384": 18,
  "1536": 10,
};

const DEFAULT_FORMAT: PlateFormat = "96";

function asPlateFormat(format: string): PlateFormat {
  return format in DIMENSIONS ? (format as PlateFormat) : DEFAULT_FORMAT;
}

export function plateDimensions(format: PlateFormat | string): { rows: number; cols: number } {
  return DIMENSIONS[asPlateFormat(format)];
}

export function plateDimensionsTuple(format: PlateFormat | string): [number, number] {
  const { rows, cols } = plateDimensions(format);
  return [rows, cols];
}

export function plateCellSizePx(format: PlateFormat | string): number {
  return CELL_SIZE_PX[asPlateFormat(format)];
}

export function rowLabel(index: number): string {
  if (index < 26) return String.fromCharCode(65 + index);
  return (
    String.fromCharCode(65 + Math.floor(index / 26) - 1) + String.fromCharCode(65 + (index % 26))
  );
}
