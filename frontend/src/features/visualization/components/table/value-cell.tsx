"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { numberAt, siblingAt } from "../../lib/dataset";
import { cellText, describeValue, inactiveBadge, qualifierText } from "../../lib/value-description";
import type { Dataset } from "../../types";

/** An aggregated value: its qualifier in front ("> 80", "≥ 10"), "—" when there is none, an
 * "Inactive k/n curves" badge, and a popover (a native button: Tab, Enter, Space) that says
 * how the value was computed. */
export function ValueCell({ ds, valueKey, i }: { ds: Dataset; valueKey: string; i: number }) {
  const v = numberAt(ds, valueKey, i);
  const q = qualifierText(siblingAt(ds, valueKey, "q", i));
  const text = v === null ? "—" : `${q ? `${q} ` : ""}${cellText(v)}`;
  const about = describeValue(ds, valueKey, i);
  const badge = inactiveBadge(ds, valueKey, i);
  return (
    <div className="flex h-full items-center justify-end gap-1.5">
      {badge && <Badge variant="warning">{badge}</Badge>}
      {about ? (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={`${text}, how ${about.title} was computed`}
              className="rounded-sm px-0.5 tabular-nums underline decoration-dotted underline-offset-4 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {text}
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64 p-3 text-xs">
            <p className="font-medium">{about.title}</p>
            <ul className="mt-1 space-y-0.5 text-muted-foreground">
              {about.lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      ) : (
        <span>{text}</span>
      )}
    </div>
  );
}
