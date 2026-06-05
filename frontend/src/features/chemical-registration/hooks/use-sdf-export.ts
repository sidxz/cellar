"use client";

import { downloadFile } from "@/shared/lib/api/download";
import { showSuccess } from "@/shared/lib/toast";
import { useCallback, useState } from "react";

/**
 * Hook for exporting molecules to SDF format.
 * Wraps the POST /api/v1/molecules/export/sdf endpoint.
 */
export function useSdfExport() {
  const [isPending, setIsPending] = useState(false);

  const exportSdf = useCallback(async (moleculeIds: string[], filename = "compounds.sdf") => {
    if (!moleculeIds.length) return;
    setIsPending(true);
    try {
      await downloadFile({
        url: "/api/v1/molecules/export/sdf",
        data: { molecule_ids: moleculeIds },
        filename,
      });
      showSuccess("SDF exported");
    } finally {
      setIsPending(false);
    }
  }, []);

  return { exportSdf, isPending };
}
