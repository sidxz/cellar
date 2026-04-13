"use client";

import { Download, ListPlus, Settings2, BookmarkPlus } from "lucide-react";
import { Button } from "@/shared/components/ui/button";

interface ResultsToolbarProps {
  resultCount: number | null;
  selectedCount: number;
  onSelectAll: () => void;
  onSelectNone: () => void;
  onExport: () => void;
  onAddToCollection: () => void;
  onCustomizeReport: () => void;
  onSaveSearch: () => void;
}

export function ResultsToolbar({
  resultCount,
  selectedCount,
  onSelectAll,
  onSelectNone,
  onExport,
  onAddToCollection,
  onCustomizeReport,
  onSaveSearch,
}: ResultsToolbarProps) {
  return (
    <div className="flex items-center gap-3 py-2">
      <span className="text-sm text-muted-foreground">
        <strong className="text-foreground">
          {resultCount?.toLocaleString() ?? "–"}
        </strong>{" "}
        results
      </span>
      {selectedCount > 0 && (
        <span className="text-sm text-indigo-400 font-medium">
          · {selectedCount} selected
        </span>
      )}
      <span className="text-xs text-muted-foreground/60">
        Select:{" "}
        <button
          type="button"
          onClick={onSelectAll}
          className="text-indigo-400 hover:text-indigo-300"
        >
          all
        </button>
        {" / "}
        <button
          type="button"
          onClick={onSelectNone}
          className="text-indigo-400 hover:text-indigo-300"
        >
          none
        </button>
      </span>

      <div className="flex-1" />

      <div className="flex gap-1.5">
        <Button variant="outline" size="sm" className="h-7 text-xs gap-1.5" onClick={onExport}>
          <Download className="h-3.5 w-3.5" />
          Export
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs gap-1.5"
          disabled={selectedCount === 0}
          onClick={onAddToCollection}
        >
          <ListPlus className="h-3.5 w-3.5" />
          Add to Collection
        </Button>
        <Button variant="outline" size="sm" className="h-7 text-xs gap-1.5" onClick={onCustomizeReport}>
          <Settings2 className="h-3.5 w-3.5" />
          Customize Report
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs gap-1.5 border-indigo-500/20 bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20"
          onClick={onSaveSearch}
        >
          <BookmarkPlus className="h-3.5 w-3.5" />
          Save Search
        </Button>
      </div>
    </div>
  );
}
