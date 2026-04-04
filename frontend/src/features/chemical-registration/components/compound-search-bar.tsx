"use client";

import { useState } from "react";
import { Search } from "lucide-react";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useSearchMolecules } from "../hooks/use-molecules";
import {
  LIFECYCLE_LABELS,
  type LifecycleStage,
  type Molecule,
} from "../types";

type SearchType = "exact" | "substructure" | "similarity";

const SEARCH_TYPE_LABELS: Record<SearchType, string> = {
  exact: "Exact (SMILES)",
  substructure: "Substructure (SMARTS)",
  similarity: "Similarity (Tanimoto)",
};

export function CompoundSearchBar() {
  const [searchType, setSearchType] = useState<SearchType>("exact");
  const [query, setQuery] = useState("");
  const [threshold, setThreshold] = useState("0.7");
  const [activeSearch, setActiveSearch] = useState<{
    search_type: string;
    query: string;
    threshold?: number;
  } | undefined>(undefined);

  const { data: results, isLoading, isError } = useSearchMolecules(activeSearch);

  const handleSearch = () => {
    if (!query.trim()) return;
    setActiveSearch({
      search_type: searchType,
      query: query.trim(),
      ...(searchType === "similarity"
        ? { threshold: parseFloat(threshold) }
        : {}),
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="grid gap-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            Search Type
          </label>
          <Select
            value={searchType}
            onValueChange={(v) => setSearchType(v as SearchType)}
          >
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
            {searchType === "substructure" ? "SMARTS Pattern" : "SMILES"}
          </label>
          <Input
            placeholder={
              searchType === "substructure"
                ? "e.g., c1ccccc1 (aromatic ring)"
                : "e.g., CC(=O)Oc1ccccc1C(=O)O"
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
        </div>

        {searchType === "similarity" && (
          <div className="grid gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Threshold
            </label>
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
        <p className="text-sm text-destructive">
          Search failed. Check your SMILES/SMARTS syntax.
        </p>
      )}

      {results && (
        <div className="rounded-lg border">
          <div className="px-4 py-2 text-sm text-muted-foreground">
            {results.length} result{results.length !== 1 ? "s" : ""} found
          </div>
          {results.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Reg #</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Formula</TableHead>
                  <TableHead>Stage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.map((mol: Molecule) => (
                  <TableRow key={mol.id}>
                    <TableCell className="font-mono text-sm">
                      {mol.registration_number}
                    </TableCell>
                    <TableCell className="font-medium">{mol.name}</TableCell>
                    <TableCell className="font-mono text-sm text-muted-foreground">
                      {mol.molecular_formula ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {LIFECYCLE_LABELS[
                          mol.lifecycle_stage as LifecycleStage
                        ] ?? mol.lifecycle_stage}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </div>
  );
}
