"use client";

import { useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import type { Ketcher } from "ketcher-core";

const KetcherEditor = dynamic(
  () => import("./ketcher-editor").then((m) => m.KetcherEditor),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="ml-3 text-sm text-muted-foreground">
          Loading structure editor...
        </span>
      </div>
    ),
  }
);

export interface StructureEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialStructure?: string;
  onApply: (structure: string) => void;
  outputFormat?: "smiles" | "smarts";
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
      const structure =
        outputFormat === "smarts"
          ? await ketcher.getSmarts()
          : await ketcher.getSmiles();

      if (structure && structure.trim()) {
        onApply(structure.trim());
        onOpenChange(false);
      }
    } catch {
      // If getSmiles/getSmarts fails, the canvas is likely empty
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
    [onOpenChange]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-0">
          <DialogTitle>
            {outputFormat === "smarts"
              ? "Draw Substructure Query"
              : "Draw Structure"}
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
          <Button
            onClick={handleApply}
            disabled={!editorReady || applying}
          >
            {applying ? "Applying..." : "Apply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
