import { Badge } from "@/shared/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import type { MergeImpactCategory } from "../types/disclosure";

export function ImpactRow({ category }: { category: MergeImpactCategory }) {
  const hasItems = category.items.length > 0;

  return (
    <Collapsible>
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted/60 transition-colors">
        {hasItems ? (
          <ChevronDown className="h-4 w-4 shrink-0 transition-transform [[data-state=open]>&]:rotate-180" />
        ) : (
          <div className="h-4 w-4" />
        )}
        <span className="flex-1 text-left">{category.label}</span>
        <Badge variant={category.is_blocker ? "destructive" : "secondary"}>{category.count}</Badge>
      </CollapsibleTrigger>
      {hasItems && (
        <CollapsibleContent className="px-9 pb-2">
          <div className="space-y-1 text-xs text-muted-foreground">
            {category.items.map((item, i) => (
              <div key={i} className="flex gap-2">
                {Object.entries(item).map(([k, v]) => (
                  <span key={k}>
                    {k.replace(/_/g, " ")}: {String(v)}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}
