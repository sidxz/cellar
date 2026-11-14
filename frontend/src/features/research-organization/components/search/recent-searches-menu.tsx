"use client";

import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { formatRelativeDate } from "@/shared/lib/format-date";
import { cn } from "@/shared/lib/utils";
import { History } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  type RecentSearch,
  useClearRecentSearches,
  useRecentSearches,
} from "../../hooks/use-recent-searches";
import type { SearchQuery } from "../../types";
import { QuerySummary, type SummaryContext, searchQueryKey } from "./query-summary";

/** A stored query without the aggregation rule riding inside it. */
export function storedCriteria(query: Record<string, unknown>): SearchQuery {
  const { aggregation: _aggregation, ...criteria } = query;
  return criteria as unknown as SearchQuery;
}

interface RecentSearchesMenuProps {
  /** The search on screen, marked in the list. */
  currentQuery: SearchQuery | null;
  summaryContext?: SummaryContext;
  /** Fill the filters with this search and run it. */
  onPick: (search: RecentSearch) => void;
}

/** "Recent searches" in the filter panel's header: the user's last 10
 *  searches, newest first; picking one fills the filters and runs it. */
export function RecentSearchesMenu({
  currentQuery,
  summaryContext,
  onPick,
}: RecentSearchesMenuProps) {
  const [open, setOpen] = useState(false);
  const { data: searches, isLoading } = useRecentSearches(10);
  const clear = useClearRecentSearches();
  const currentKey = currentQuery ? searchQueryKey(currentQuery) : null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="text-muted-foreground">
          <History className="mr-1.5 h-4 w-4" />
          Recent searches
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        collisionPadding={16}
        className="flex max-h-(--radix-popover-content-available-height) w-[min(36rem,calc(100vw-2rem))] flex-col p-0"
      >
        <p className="border-b border-border px-3 py-2 text-sm font-semibold">Recent searches</p>
        <div className="min-h-0 flex-1 overflow-y-auto py-1">
          {isLoading ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">Loading…</p>
          ) : !searches?.length ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              Searches you run appear here.
            </p>
          ) : (
            <ul>
              {searches.map((search) => {
                const query = storedCriteria(search.query);
                const onScreen = currentKey === searchQueryKey(query);
                const count = search.result_count;
                return (
                  <li key={search.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        onPick(search);
                      }}
                      className={cn(
                        "flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none",
                        onScreen && "bg-primary/5",
                      )}
                    >
                      <QuerySummary
                        query={query}
                        context={summaryContext}
                        className="line-clamp-2 text-sm"
                      />
                      <span className="text-xs text-muted-foreground">
                        {count != null &&
                          `${count.toLocaleString()} compound${count === 1 ? "" : "s"} · `}
                        {formatRelativeDate(search.ran_at)}
                        {onScreen && " · on screen"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs">
          <Link href="/saved-searches" className="text-primary hover:underline">
            Saved searches →
          </Link>
          {!!searches?.length && (
            <button
              type="button"
              onClick={() => clear.mutate()}
              disabled={clear.isPending}
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Clear history
            </button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
