"use client";

import { Input } from "@/shared/components/ui/input";
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

  return (
    <div className="relative">
      <Input
        value={selected ? `${selected.name} (${selected.email})` : query}
        onChange={(e) => {
          setQuery(e.target.value);
          if (selectedId) onSelect(null);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
      />
      {selectedId && (
        <button
          type="button"
          onClick={() => {
            onSelect(null);
            setQuery("");
          }}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        >
          &times;
        </button>
      )}
      {open && !selectedId && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md max-h-48 overflow-y-auto">
          {isLoading && <div className="px-3 py-2 text-sm text-muted-foreground">Loading...</div>}
          {!isLoading && members && members.length === 0 && (
            <div className="px-3 py-2 text-sm text-muted-foreground">No members found</div>
          )}
          {members?.map((m) => (
            <button
              key={m.user_id}
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              onClick={() => {
                onSelect(m.user_id);
                setQuery("");
                setOpen(false);
              }}
            >
              <span className="font-medium">{m.name}</span>
              <span className="text-muted-foreground">{m.email}</span>
              <span className="ml-auto text-xs text-muted-foreground">{m.role}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
