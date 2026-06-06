"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { useState } from "react";

interface MemberSelectorProps {
  selectedId: string | null;
  onSelect: (userId: string | null) => void;
  /** Placeholder text for the search input */
  placeholder?: string;
}

/**
 * Searchable member selector — lists workspace members from Sentinel.
 * Returns the user_id (UUID) of the selected member.
 */
export function MemberSelector({
  selectedId,
  onSelect,
  placeholder = "Search by name or email...",
}: MemberSelectorProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const { data: members, isLoading } = useWorkspaceMembers(query.length >= 1 ? query : undefined);

  const selected = members?.find((m) => m.user_id === selectedId);
  const displayValue = selected ? `${selected.name} (${selected.email})` : query;

  return (
    <SearchCombobox
      searchValue={displayValue}
      onSearchChange={(value) => {
        setQuery(value);
        if (selectedId) onSelect(null);
        setOpen(true);
      }}
      items={members ?? []}
      getItemKey={(m) => m.user_id}
      renderItem={(m) => (
        <span className="flex w-full items-center gap-2 text-sm">
          <span className="font-medium">{m.name}</span>
          <span className="text-muted-foreground">{m.email}</span>
          <span className="ml-auto text-xs text-muted-foreground">{m.role}</span>
        </span>
      )}
      onSelect={(m) => {
        onSelect(m.user_id);
        setQuery("");
        setOpen(false);
      }}
      isLoading={isLoading}
      open={open && !selectedId}
      onOpenChange={setOpen}
      onInputFocus={() => setOpen(true)}
      placeholder={placeholder}
      emptyMessage="No members found"
      loadingMessage="Loading..."
      onClear={
        selectedId
          ? () => {
              onSelect(null);
              setQuery("");
            }
          : undefined
      }
      clearAriaLabel="Clear selection"
    />
  );
}
