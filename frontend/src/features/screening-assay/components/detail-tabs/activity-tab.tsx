"use client";

import type { Protocol } from "../../types";

interface ActivityTabProps {
  protocol: Protocol;
  protocolId: string;
}

export function ActivityTab({ protocolId }: ActivityTabProps) {
  return (
    <div className="p-8 text-center text-muted-foreground">
      Activity tab — coming in next task
    </div>
  );
}
