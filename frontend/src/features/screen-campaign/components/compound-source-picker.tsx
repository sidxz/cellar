"use client";

/**
 * CompoundSourcePicker — reusable source-selector subcomponent shared between
 * CreateCampaignDialog (8.1) and the Re-seed flow (8.6).
 *
 * Renders a Tabs panel with four source kinds:
 *   explicit_list, collection, saved_search (disabled — backend rejects),
 *   derived_from_campaign
 */

import { useState } from "react";
import { Search } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Badge } from "@/shared/components/ui/badge";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { useMoleculeSearch } from "@/features/chemical-registration/hooks/use-molecules";
import { useCollections } from "@/features/research-organization/hooks/use-collections";
import { useSavedSearches } from "@/features/research-organization/hooks/use-saved-searches";
import { useCampaignsByProject } from "../lib/hooks";
import type {
  ExplicitListSourceDTO,
  CollectionSourceDTO,
  SavedSearchSourceDTO,
  DerivedFromCampaignSourceDTO,
} from "@/shared/lib/api/model";

export type CompoundSourceValue =
  | ExplicitListSourceDTO
  | CollectionSourceDTO
  | SavedSearchSourceDTO
  | DerivedFromCampaignSourceDTO;

interface CompoundSourcePickerProps {
  projectId: string;
  value: CompoundSourceValue | null;
  onChange: (value: CompoundSourceValue | null) => void;
}

const DECISION_OPTIONS = [
  { value: "selected", label: "Selected" },
  { value: "deferred", label: "Deferred" },
  { value: "rejected", label: "Rejected" },
];

export function CompoundSourcePicker({
  projectId,
  value,
  onChange,
}: CompoundSourcePickerProps) {
  const [activeTab, setActiveTab] = useState<string>(
    value && "kind" in value ? (value.kind ?? "explicit_list") : "explicit_list",
  );

  // Explicit list state
  const [moleculeSearch, setMoleculeSearch] = useState("");
  const [selectedMoleculeIds, setSelectedMoleculeIds] = useState<string[]>(
    value && "molecule_ids" in value ? (value as ExplicitListSourceDTO).molecule_ids : [],
  );
  const { data: searchResults, isLoading: searchLoading } = useMoleculeSearch(moleculeSearch);

  // Collection state
  const [collectionId, setCollectionId] = useState<string>(
    value && "collection_id" in value ? (value as CollectionSourceDTO).collection_id : "",
  );
  const { data: collections } = useCollections([projectId]);

  // SavedSearch state
  const [savedSearchId, setSavedSearchId] = useState<string>(
    value && "saved_search_id" in value ? (value as SavedSearchSourceDTO).saved_search_id : "",
  );
  const { data: savedSearches } = useSavedSearches(projectId);

  // DerivedFromCampaign state
  const [parentCampaignId, setParentCampaignId] = useState<string>(
    value && "campaign_id" in value ? (value as DerivedFromCampaignSourceDTO).campaign_id : "",
  );
  const [decisionFilter, setDecisionFilter] = useState<string[]>(
    value && "decision_filter" in value
      ? ((value as DerivedFromCampaignSourceDTO).decision_filter ?? [])
      : ["selected"],
  );
  const { data: campaigns } = useCampaignsByProject(projectId);
  const closedCampaigns = campaigns?.filter((c) => c.status !== "draft") ?? [];

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    onChange(null);
  };

  const toggleMolecule = (id: string, regNumber: string) => {
    const next = selectedMoleculeIds.includes(id)
      ? selectedMoleculeIds.filter((x) => x !== id)
      : [...selectedMoleculeIds, id];
    setSelectedMoleculeIds(next);
    onChange(next.length > 0 ? { kind: "explicit_list", molecule_ids: next } : null);
    // suppress "regNumber unused" — it is shown in the result row via map
    void regNumber;
  };

  const handleCollectionChange = (id: string) => {
    setCollectionId(id);
    onChange({ kind: "collection", collection_id: id });
  };

  const handleSavedSearchChange = (id: string) => {
    setSavedSearchId(id);
    onChange({ kind: "saved_search", saved_search_id: id });
  };

  const handleParentCampaignChange = (id: string) => {
    setParentCampaignId(id);
    onChange({
      kind: "derived_from_campaign",
      campaign_id: id,
      decision_filter: decisionFilter,
    });
  };

  const handleDecisionFilterChange = (decision: string, checked: boolean) => {
    const next = checked
      ? [...decisionFilter, decision]
      : decisionFilter.filter((d) => d !== decision);
    setDecisionFilter(next);
    if (parentCampaignId) {
      onChange({
        kind: "derived_from_campaign",
        campaign_id: parentCampaignId,
        decision_filter: next,
      });
    }
  };

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange}>
      <TabsList className="w-full">
        <TabsTrigger value="explicit_list" className="flex-1">
          Explicit List
        </TabsTrigger>
        <TabsTrigger value="collection" className="flex-1">
          Collection
        </TabsTrigger>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <TabsTrigger value="saved_search" className="flex-1 opacity-50" disabled>
                Saved Search
              </TabsTrigger>
            </TooltipTrigger>
            <TooltipContent>
              Saved search sources are not yet supported in the backend (returns
              ValidationError). Coming in a follow-up.
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TabsTrigger value="derived_from_campaign" className="flex-1">
          From Campaign
        </TabsTrigger>
      </TabsList>

      {/* ── Explicit list ── */}
      <TabsContent value="explicit_list" className="space-y-3 pt-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Search by name or reg number..."
            value={moleculeSearch}
            onChange={(e) => setMoleculeSearch(e.target.value)}
          />
        </div>
        {selectedMoleculeIds.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <span className="text-xs text-muted-foreground">
              {selectedMoleculeIds.length} selected
            </span>
          </div>
        )}
        <div className="max-h-48 overflow-y-auto rounded border divide-y text-sm">
          {searchLoading && (
            <p className="p-2 text-muted-foreground">Searching...</p>
          )}
          {!searchLoading && moleculeSearch.length >= 2 && !searchResults?.length && (
            <p className="p-2 text-muted-foreground">No results</p>
          )}
          {moleculeSearch.length < 2 && (
            <p className="p-2 text-muted-foreground">Type at least 2 characters to search</p>
          )}
          {searchResults?.map((mol) => (
            <div
              key={mol.id}
              className="flex items-center gap-2 px-3 py-2 hover:bg-muted/50 cursor-pointer"
              onClick={() => toggleMolecule(mol.id, mol.registration_number)}
            >
              <Checkbox
                checked={selectedMoleculeIds.includes(mol.id)}
                onCheckedChange={(checked) => {
                  if (typeof checked === "boolean") toggleMolecule(mol.id, mol.registration_number);
                }}
              />
              <span className="font-mono text-xs text-muted-foreground">
                {mol.registration_number}
              </span>
              <span className="truncate">{mol.name}</span>
            </div>
          ))}
        </div>
        {selectedMoleculeIds.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {selectedMoleculeIds.length} compound(s) selected
          </p>
        )}
      </TabsContent>

      {/* ── Collection ── */}
      <TabsContent value="collection" className="space-y-3 pt-3">
        <Label>Collection</Label>
        <Select value={collectionId} onValueChange={handleCollectionChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select a collection..." />
          </SelectTrigger>
          <SelectContent>
            {collections?.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
                {c.molecule_count != null && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    ({c.molecule_count})
                  </span>
                )}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TabsContent>

      {/* ── Saved Search (disabled) ── */}
      <TabsContent value="saved_search" className="space-y-3 pt-3">
        <Label>Saved Search</Label>
        <Select value={savedSearchId} onValueChange={handleSavedSearchChange} disabled>
          <SelectTrigger>
            <SelectValue placeholder="Select a saved search..." />
          </SelectTrigger>
          <SelectContent>
            {savedSearches?.map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-destructive">
          Saved search sources currently return a backend ValidationError. This
          tab will be enabled in a follow-up once the backend supports the
          SavedSearchSource kind.
        </p>
      </TabsContent>

      {/* ── Derived from campaign ── */}
      <TabsContent value="derived_from_campaign" className="space-y-3 pt-3">
        <Label>Parent Campaign</Label>
        <Select value={parentCampaignId} onValueChange={handleParentCampaignChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select a closed campaign..." />
          </SelectTrigger>
          <SelectContent>
            {closedCampaigns.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
                <Badge variant="secondary" className="ml-2 text-xs">
                  {c.status}
                </Badge>
              </SelectItem>
            ))}
            {closedCampaigns.length === 0 && (
              <SelectItem value="__none__" disabled>
                No closed campaigns in this project
              </SelectItem>
            )}
          </SelectContent>
        </Select>

        {parentCampaignId && (
          <div className="space-y-2">
            <Label>Include decisions</Label>
            {DECISION_OPTIONS.map((opt) => (
              <div key={opt.value} className="flex items-center gap-2">
                <Checkbox
                  id={`decision-${opt.value}`}
                  checked={decisionFilter.includes(opt.value)}
                  onCheckedChange={(checked) =>
                    handleDecisionFilterChange(opt.value, checked === true)
                  }
                />
                <label
                  htmlFor={`decision-${opt.value}`}
                  className="text-sm cursor-pointer"
                >
                  {opt.label}
                </label>
              </div>
            ))}
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}
