"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { ProtocolList } from "@/features/screening-assay";

interface AddProtocolDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddProtocolDialog({
  projectId,
  open,
  onOpenChange,
}: AddProtocolDialogProps) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);

  const handleSelect = async (protocolId: string) => {
    setAdding(true);
    try {
      await customInstance({
        url: `/api/v1/protocols/${protocolId}/projects/${projectId}`,
        method: "POST",
      });
      qc.invalidateQueries({ queryKey: ["protocols"] });
      showSuccess("Protocol added to project");
      onOpenChange(false);
    } finally {
      setAdding(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Add Protocol to Project</DialogTitle>
        </DialogHeader>
        <div className={adding ? "pointer-events-none opacity-50" : ""}>
          <ProtocolList onSelect={handleSelect} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
