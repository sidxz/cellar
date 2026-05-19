"use client";

import { History } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/shared/components/ui/popover";
import { formatRelativeDate } from "@/shared/lib/format-date";
import type { CurveEditHistoryEventBody } from "@/shared/lib/api/model";

interface CurveEditHistoryProps {
  /** Newest-first audit events for the curve. Comes straight from
   *  `GET /api/v1/dose-response-curves/{id}/edit-history`. */
  events: CurveEditHistoryEventBody[];
  isLoading?: boolean;
}

/**
 * Small "History" button next to "Edit Points" on the DR chart toolbar.
 * Opens a popover listing prior point-exclusion edits — reason +
 * relative timestamp + a short user-id prefix (Task 3.1 doesn't return
 * a resolved display name yet).
 */
export function CurveEditHistory({ events, isLoading }: CurveEditHistoryProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2"
          aria-label="View edit history"
        >
          <History className="h-3.5 w-3.5" />
          <span className="ml-1.5 text-xs">History</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-96 max-h-96 overflow-y-auto"
      >
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : events.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No edit history yet.
          </div>
        ) : (
          <ol className="space-y-3">
            {events.map((e) => (
              <li
                key={e.id}
                className="text-sm border-l-2 border-muted pl-3"
              >
                <div className="font-medium">{e.reason ?? "Edit"}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {formatRelativeDate(e.timestamp)}
                  {e.user_id ? ` · by ${e.user_id.slice(0, 8)}…` : ""}
                </div>
              </li>
            ))}
          </ol>
        )}
      </PopoverContent>
    </Popover>
  );
}
