"use client";

import { Download, ListPlus, Settings2, BookmarkPlus } from "lucide-react";
import { Button } from "@/shared/components/ui/button";

interface ResultsToolbarProps {
  resultCount: number | null;
  selectedCount: number;
  onExport: () => void;
  onAddToCollection: () => void;
  onCustomizeReport: () => void;
  onSaveSearch: () => void;
}

export function ResultsToolbar({
  resultCount,
  selectedCount,
  onExport,
  onAddToCollection,
  onCustomizeReport,
  onSaveSearch,
}: ResultsToolbarProps) {
  return (
    <div className="flex items-center justify-between border-b px-3 py-2">
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {resultCount != null
            ? `${resultCount.toLocaleString()} result${resultCount === 1 ? "" : "s"}`
            : "No results"}
        </span>
        {selectedCount > 0 && (
          <span className="text-sm font-medium">
            {selectedCount} selected
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onExport}>
          <Download className="mr-1.5 h-4 w-4" />
          Export
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onAddToCollection}
          disabled={selectedCount === 0}
        >
          <ListPlus className="mr-1.5 h-4 w-4" />
          Add to Collection
        </Button>
        <Button variant="outline" size="sm" onClick={onCustomizeReport}>
          <Settings2 className="mr-1.5 h-4 w-4" />
          Customize Report
        </Button>
        <Button variant="outline" size="sm" onClick={onSaveSearch}>
          <BookmarkPlus className="mr-1.5 h-4 w-4" />
          Save Search
        </Button>
      </div>
    </div>
  );
}
