"use client";

import { Button } from "@/shared/components/ui/button";
import type { ConditionSuggestion } from "../../hooks/use-method-suggestions";

/** Conditions read from the method, each with the line it came from. Added only by the person;
 *  the stated value is evidence, since each run records its own. */
export function SuggestedConditions({
  suggestions,
  onAdd,
  onDismiss,
}: {
  suggestions: ConditionSuggestion[];
  onAdd: (s: ConditionSuggestion) => void;
  onDismiss: (s: ConditionSuggestion) => void;
}) {
  if (suggestions.length === 0) return null;
  return (
    <div className="grid gap-2 rounded-md border border-dashed p-3">
      <p className="text-xs text-muted-foreground">
        Suggested from the method. Check each against the text; each run records its own value.
      </p>
      {suggestions.map((s) => (
        <div key={s.name} className="flex items-start gap-2">
          <div className="grid min-w-0 flex-1 gap-0.5">
            <span className="text-sm font-medium">
              {s.name}
              {s.unit && <span className="font-normal text-muted-foreground"> ({s.unit})</span>}
            </span>
            {s.evidence.map((e) => (
              <Quote key={`${e.value}|${e.quote}`} text={e.quote} value={e.value} />
            ))}
          </div>
          <Button type="button" size="sm" variant="outline" onClick={() => onAdd(s)}>
            Add {s.name}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label={`Dismiss ${s.name}`}
            onClick={() => onDismiss(s)}
          >
            Dismiss
          </Button>
        </div>
      ))}
    </div>
  );
}

/** The method's line with the value marked. */
function Quote({ text, value }: { text: string; value: string }) {
  const i = text.indexOf(value);
  return (
    <q className="text-xs text-muted-foreground">
      {i < 0 ? (
        text
      ) : (
        <>
          {text.slice(0, i)}
          <mark className="rounded-sm bg-amber-100 px-0.5 text-foreground dark:bg-amber-900/60">
            {value}
          </mark>
          {text.slice(i + value.length)}
        </>
      )}
    </q>
  );
}
