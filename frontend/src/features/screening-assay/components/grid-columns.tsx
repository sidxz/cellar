import { StructureThumbnail } from "@/shared/components/chemistry";
import type { ColDef, ICellRendererParams } from "ag-grid-community";

// ---------------------------------------------------------------------------
// Shared AG Grid column factories for screening-assay result grids.
//
// The "Structure" column renders a chemical-structure thumbnail (or a "--"
// placeholder when the row has no SMILES) and is byte-identical across the
// run dose-response grid and the protocol activity grid. Extracted here so a
// change to the thumbnail size / placeholder / width lands in one place.
// ---------------------------------------------------------------------------

/** Default rendered thumbnail size (px) for the Structure column. */
const STRUCTURE_THUMBNAIL_SIZE = 104;

/**
 * A non-sortable "Structure" column rendering a {@link StructureThumbnail}
 * for the row's SMILES (or "--" when absent).
 *
 * @param getSmiles reads the SMILES off the row data (rows differ per grid).
 */
export function structureColumn<TRow>(
  getSmiles: (row: TRow) => string | null | undefined,
): ColDef<TRow> {
  return {
    headerName: "Structure",
    colId: "structure",
    width: 130,
    sortable: false,
    cellRenderer: (params: ICellRendererParams<TRow>) => {
      const smiles = params.data ? getSmiles(params.data) : null;
      if (!smiles) return <span className="text-muted-foreground">--</span>;
      return (
        <div className="flex h-full items-center justify-center py-1">
          <StructureThumbnail smiles={smiles} size={STRUCTURE_THUMBNAIL_SIZE} />
        </div>
      );
    },
  };
}
