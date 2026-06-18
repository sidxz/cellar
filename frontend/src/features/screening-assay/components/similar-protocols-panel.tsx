"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { X } from "lucide-react";
import { useState } from "react";
import {
  type SimilarProtocol,
  type SimilarProtocolDraft,
  useSimilarProtocols,
} from "../hooks/use-similar-protocols";

interface Props {
  draft: SimilarProtocolDraft;
  onLogRun: (protocolId: string) => void;
}

export function SimilarProtocolsPanel({ draft, onLogRun }: Props) {
  const [dismissed, setDismissed] = useState(false);
  const { data } = useSimilarProtocols(draft);
  const matches: SimilarProtocol[] = data ?? [];
  if (dismissed || matches.length === 0) return null;

  const runCandidate = matches.find((m) => m.is_run_candidate);
  const others = matches.filter((m) => m !== runCandidate);

  return (
    <div className="rounded-md border border-amber-300/60 bg-amber-50/60 p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-amber-900">
          {runCandidate ? "This looks like a run of an existing method" : "Similar protocols exist"}
        </span>
        <button
          type="button"
          aria-label="Dismiss suggestions"
          onClick={() => setDismissed(true)}
          className="text-amber-700 hover:text-amber-900"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {runCandidate && (
        <div className="mb-2 rounded border bg-white p-2">
          <div className="flex items-center gap-2">
            <span className="font-medium">{runCandidate.name}</span>
            <Badge variant="secondary">{runCandidate.protocol_type}</Badge>
            {runCandidate.targets.map((t) => (
              <Badge key={t.id} variant="outline">
                {t.name}
              </Badge>
            ))}
          </div>
          <Button
            type="button"
            size="sm"
            className="mt-2"
            onClick={() => onLogRun(runCandidate.id)}
          >
            Log a run of this
          </Button>
        </div>
      )}

      {others.length > 0 && (
        <ul className="space-y-1">
          {others.map((m) => (
            <li key={m.id} className="flex items-center gap-2 text-muted-foreground">
              <span>{m.name}</span>
              <Badge variant="outline">{m.protocol_type}</Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
