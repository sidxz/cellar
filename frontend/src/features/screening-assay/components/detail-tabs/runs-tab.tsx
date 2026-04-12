"use client";

import type { Protocol } from "../../types";

interface RunsTabProps {
  protocol: Protocol;
  protocolId: string;
}

export function RunsTab({ protocolId }: RunsTabProps) {
  return (
    <div className="p-8 text-center text-muted-foreground">
      Runs tab — coming in next task
    </div>
  );
}
