"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/shared/components/ui/skeleton";

/**
 * Dynamic (no-SSR) exports for chemistry components.
 *
 * RDKit.js WASM uses `require('fs')` in its Node.js detection path,
 * which fails during SSR/build. These dynamic imports ensure the WASM
 * module is only loaded client-side — same pattern as react-plotly.js.
 */

export const StructureRenderer = dynamic(
  () =>
    import("./structure-renderer").then((mod) => mod.StructureRenderer),
  {
    ssr: false,
    loading: () => <Skeleton style={{ width: 300, height: 200 }} />,
  }
);

export const StructureThumbnail = dynamic(
  () =>
    import("./structure-thumbnail").then((mod) => mod.StructureThumbnail),
  {
    ssr: false,
    loading: () => (
      <div className="h-10 w-10 rounded bg-muted" />
    ),
  }
);

export { StructureEditorDialog } from "./structure-editor-dialog";
export type { StructureEditorDialogProps } from "./structure-editor-dialog";
