"use client";

import { MoleculeList } from "@/features/chemical-registration";
import { DisclosureConflictList } from "@/features/chemical-registration/components/disclosure-conflict-list";
import { useConflictDisclosures } from "@/features/chemical-registration/hooks/use-disclosures";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { useState } from "react";

type Tab = "compounds" | "conflicts";

export default function CompoundsPage() {
  const [tab, setTab] = useState<Tab>("compounds");
  const { data: conflicts } = useConflictDisclosures();
  const conflictCount = conflicts?.length ?? 0;

  return (
    <div>
      <div className="mb-4 flex gap-2 border-b pb-2">
        <Button
          variant={tab === "compounds" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setTab("compounds")}
        >
          Compounds
        </Button>
        <Button
          variant={tab === "conflicts" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setTab("conflicts")}
        >
          Conflicts
          {conflictCount > 0 && (
            <Badge variant="destructive" className="ml-2">
              {conflictCount}
            </Badge>
          )}
        </Button>
      </div>

      {tab === "compounds" ? <MoleculeList /> : <DisclosureConflictList />}
    </div>
  );
}
