"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import type { Ketcher } from "ketcher-core";
import { Loader2 } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useRef, useState } from "react";

const KetcherEditor = dynamic(() => import("./ketcher-editor").then((m) => m.KetcherEditor), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="ml-3 text-sm text-muted-foreground">Loading structure editor...</span>
    </div>
  ),
});

export type StructureEditorOutputFormat = "smiles" | "smarts" | "auto";

export interface StructureEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialStructure?: string;
  /** Called with the editor's output. The second arg is the resolved
   *  format — informative for "auto" mode so callers can tag downstream
   *  state (e.g. `query_kind` on a substructure criterion). */
  onApply: (structure: string, format: "smiles" | "smarts") => void;
  outputFormat?: StructureEditorOutputFormat;
}

export function StructureEditorDialog({
  open,
  onOpenChange,
  initialStructure,
  onApply,
  outputFormat = "smiles",
}: StructureEditorDialogProps) {
  const ketcherRef = useRef<Ketcher | null>(null);
  const [editorReady, setEditorReady] = useState(false);
  const [applying, setApplying] = useState(false);

  const handleInit = useCallback(() => {
    setEditorReady(true);
  }, []);

  const handleApply = useCallback(async () => {
    const ketcher = ketcherRef.current;
    if (!ketcher) return;

    setApplying(true);
    try {
      // "auto" tries SMILES first; if Ketcher can't express the drawing
      // as SMILES (query atoms / R-groups / atom lists present), fall
      // back to SMARTS. SMILES export throws or returns empty for
      // drawings with query features.
      let structure: string | null = null;
      let resolvedFormat: "smiles" | "smarts" = "smiles";
      if (outputFormat === "smarts") {
        structure = await ketcher.getSmarts();
        resolvedFormat = "smarts";
      } else if (outputFormat === "smiles") {
        structure = await ketcher.getSmiles();
        resolvedFormat = "smiles";
      } else {
        // auto
        try {
          const smi = await ketcher.getSmiles();
          if (smi && smi.trim()) {
            structure = smi;
            resolvedFormat = "smiles";
          }
        } catch {
          // Drawing has query features Ketcher can't render as SMILES.
        }
        if (!structure) {
          structure = await ketcher.getSmarts();
          resolvedFormat = "smarts";
        }
      }

      if (structure && structure.trim()) {
        onApply(structure.trim(), resolvedFormat);
        onOpenChange(false);
      }
    } catch {
      // Empty canvas or other Ketcher hiccup — close silently.
    } finally {
      setApplying(false);
    }
  }, [outputFormat, onApply, onOpenChange]);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setEditorReady(false);
        ketcherRef.current = null;
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange],
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-0">
          <DialogTitle>
            {outputFormat === "smiles" ? "Draw Structure" : "Draw Substructure Query"}
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0 px-6">
          {open && (
            <KetcherEditor
              initialStructure={initialStructure}
              onInit={handleInit}
              ketcherRef={ketcherRef}
            />
          )}
        </div>

        <DialogFooter className="px-6 pb-6 pt-2">
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleApply} disabled={!editorReady || applying}>
            {applying ? "Applying..." : "Apply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
