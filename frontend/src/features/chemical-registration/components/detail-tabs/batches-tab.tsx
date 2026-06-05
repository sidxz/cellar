"use client";

import { BatchList } from "@/features/inventory/components/batch-list";
import { CreateBatchDialog } from "@/features/inventory/components/create-batch-dialog";
import { Button } from "@/shared/components/ui/button";
import { Plus } from "lucide-react";
import { useState } from "react";

interface BatchesTabProps {
  moleculeId: string;
  moleculeMw?: number;
  detectedSalt?: {
    salt_smiles: string;
    salt_fragment_mw: number;
    stoichiometry: number;
  } | null;
}

export function BatchesTab({ moleculeId, moleculeMw, detectedSalt }: BatchesTabProps) {
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Batch
        </Button>
      </div>
      <BatchList moleculeId={moleculeId} />
      <CreateBatchDialog
        moleculeId={moleculeId}
        moleculeMw={moleculeMw}
        detectedSalt={detectedSalt}
        open={showCreate}
        onOpenChange={setShowCreate}
      />
    </div>
  );
}
