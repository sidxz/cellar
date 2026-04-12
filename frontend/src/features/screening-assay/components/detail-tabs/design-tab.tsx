"use client";

import type { Protocol } from "../../types";

interface DesignTabProps {
  protocol: Protocol;
  protocolId: string;
}

export function DesignTab({ protocolId }: DesignTabProps) {
  return (
    <div className="p-8 text-center text-muted-foreground">
      Design tab — coming in next task
    </div>
  );
}
