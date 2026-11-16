"use client";

import { RGroupCorePicker } from "@/features/sar-analysis/components/rgroup-core-picker";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useState } from "react";

/** "R-groups…": the SAR core picker over the dataset's compounds with a structure; Apply
 * hands the picked (or drawn) core to the page, which starts the decomposition. */
export function RGroupsDialog({
  open,
  onOpenChange,
  moleculeIds,
  onApply,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  moleculeIds: string[];
  onApply: (coreSmiles: string) => void;
}) {
  const [core, setCore] = useState<string | null>(null);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* No taller than the screen: the picker scrolls, the title and footer stay. */}
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add R-group columns</DialogTitle>
          <DialogDescription>
            Each R position becomes a column; compounds that don't match the core get none.
          </DialogDescription>
        </DialogHeader>
        <div className="-m-1 min-h-0 overflow-y-auto p-1">
          <RGroupCorePicker moleculeIds={moleculeIds} coreSmiles={core} onCoreChange={setCore} />
        </div>
        <p className="text-sm text-muted-foreground">
          Decompose {moleculeIds.length.toLocaleString()} compounds against this core
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!core}
            onClick={() => {
              if (!core) return;
              onApply(core);
              onOpenChange(false);
            }}
          >
            Add R-group columns
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
