"use client";

import { StructureEditorDialog } from "@/shared/components/chemistry";
import { StructureRenderer } from "@/shared/components/chemistry";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { detectQueryKind } from "@/shared/lib/rdkit/detect-query-kind";
import { Pencil, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { type SearchResult, useMoleculeSearch, useSearchMolecules } from "../hooks/use-molecules";
import { LIFECYCLE_LABELS, type LifecycleStage } from "../types";

type SearchType = "name_id" | "exact" | "substructure" | "similarity";

const SEARCH_TYPE_LABELS: Record<SearchType, string> = {
  name_id: "By Name / ID",
  exact: "Exact (SMILES)",
  substructure: "Substructure",
  similarity: "Similarity (Tanimoto)",
};

export function CompoundSearchBar() {
  const router = useRouter();
  const [searchType, setSearchType] = useState<SearchType>("name_id");
  const [query, setQuery] = useState("");
  const [threshold, setThreshold] = useState("0.7");
  const [activeTextSearch, setActiveTextSearch] = useState("");
  const [activeStructSearch, setActiveStructSearch] = useState<
    | {
        search_type: string;
        query: string;
        threshold?: number;
        query_kind?: "smiles" | "smarts";
      }
    | undefined
  >(undefined);
  // Resolved format from the editor (or auto-detected from typed input)
  // — sent as ?query_kind to the BE for substructure searches.
  const [drawnQueryKind, setDrawnQueryKind] = useState<"smiles" | "smarts" | undefined>(undefined);

  const isTextMode = searchType === "name_id";
  const [editorOpen, setEditorOpen] = useState(false);

  // Text search (name/ID) uses the list endpoint with ?q=
  const {
    data: textResults,
    isLoading: textLoading,
    isError: textError,
  } = useMoleculeSearch(activeTextSearch);
  // Structure search uses the dedicated search endpoint
  const {
    data: structResults,
    isLoading: structLoading,
    isError: structError,
  } = useSearchMolecules(activeStructSearch);

  const textData: SearchResult[] | undefined = textResults?.map((m) => ({
    molecule: m,
    similarity: null,
  }));
  const results = isTextMode ? textData : structResults;
  const isLoading = isTextMode ? textLoading : structLoading;
  const isError = isTextMode ? textError : structError;
  const showSimilarity = searchType === "similarity";

  const handleSearch = () => {
    if (!query.trim()) return;
    if (isTextMode) {
      setActiveTextSearch(query.trim());
      setActiveStructSearch(undefined);
    } else {
      // For substructure: prefer the format the editor resolved to;
      // for typed input, run the same SMARTS-only sigil heuristic the
      // search panel uses.
      const queryKind: "smiles" | "smarts" | undefined =
        searchType === "substructure"
          ? (drawnQueryKind ?? detectQueryKind(query.trim()))
          : undefined;
      setActiveStructSearch({
        search_type: searchType,
        query: query.trim(),
        ...(searchType === "similarity" ? { threshold: Number.parseFloat(threshold) } : {}),
        ...(queryKind ? { query_kind: queryKind } : {}),
      });
      setActiveTextSearch("");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="grid gap-1.5">
          <label className="text-xs font-medium text-muted-foreground">Search Type</label>
          <Select value={searchType} onValueChange={(v) => setSearchType(v as SearchType)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(SEARCH_TYPE_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid flex-1 gap-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            {isTextMode
              ? "Name, Reg #, Formula, or Identifier"
              : searchType === "substructure"
                ? "SMARTS Pattern"
                : "SMILES"}
          </label>
          <Input
            placeholder={
              isTextMode
                ? "e.g., CV-00001, Aspirin, C9H8O4, CHEMBL25..."
                : searchType === "substructure"
                  ? "e.g., c1ccccc1 (aromatic ring)"
                  : "e.g., CC(=O)Oc1ccccc1C(=O)O"
            }
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              // Typing invalidates the draw-format hint — fall back to
              // the heuristic on next search.
              setDrawnQueryKind(undefined);
            }}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
        </div>

        {searchType === "similarity" && (
          <div className="grid gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">Threshold</label>
            <Input
              type="number"
              className="w-[80px]"
              step="0.05"
              min="0"
              max="1"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
          </div>
        )}

        {!isTextMode && (
          <Button
            variant="outline"
            size="icon"
            onClick={() => setEditorOpen(true)}
            title="Draw structure"
          >
            <Pencil className="h-4 w-4" />
          </Button>
        )}

        <Button onClick={handleSearch} disabled={!query.trim()}>
          <Search className="mr-2 h-4 w-4" />
          Search
        </Button>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-sm text-destructive">Search failed. Check your SMILES/SMARTS syntax.</p>
      )}

      {results && (
        <div className="rounded-lg border">
          <div className="px-4 py-2 text-sm text-muted-foreground">
            {results.length} result{results.length !== 1 ? "s" : ""} found
          </div>
          {results.length > 0 && (
            <div className="divide-y">
              {results.map((r) => (
                <div
                  key={r.molecule.id}
                  className="flex gap-4 p-4 cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => router.push(`/compounds/${r.molecule.id}`)}
                >
                  {/* Structure */}
                  <div className="shrink-0">
                    {r.molecule.structure?.smiles ? (
                      <StructureRenderer
                        smiles={r.molecule.structure.smiles}
                        width={200}
                        height={160}
                      />
                    ) : (
                      <div
                        className="flex items-center justify-center rounded border border-dashed text-xs text-muted-foreground"
                        style={{ width: 200, height: 160 }}
                      >
                        Undisclosed
                      </div>
                    )}
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium">
                        {r.molecule.registration_number}
                      </span>
                      <Badge variant="outline">
                        {LIFECYCLE_LABELS[r.molecule.lifecycle_stage as LifecycleStage] ??
                          r.molecule.lifecycle_stage}
                      </Badge>
                      {showSimilarity && r.similarity != null && (
                        <span
                          className={
                            r.similarity > 0.8
                              ? "text-success font-medium text-sm"
                              : r.similarity > 0.6
                                ? "text-yellow-400 text-sm"
                                : "text-muted-foreground text-sm"
                          }
                        >
                          {(r.similarity * 100).toFixed(1)}%
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-medium truncate">{r.molecule.name}</p>
                    <p className="text-xs font-mono text-muted-foreground">
                      {r.molecule.molecular_formula ?? "—"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {!isTextMode && (
        <StructureEditorDialog
          open={editorOpen}
          onOpenChange={setEditorOpen}
          initialStructure={query}
          onApply={(s, format) => {
            setQuery(s);
            setDrawnQueryKind(searchType === "substructure" ? format : undefined);
          }}
          outputFormat={searchType === "substructure" ? "auto" : "smiles"}
        />
      )}
    </div>
  );
}
