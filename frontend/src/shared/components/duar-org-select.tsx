"use client";

import { SearchableSelect } from "@/shared/components/searchable-select";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgs } from "@/shared/hooks/use-orgs";

/** Pick one of Duar's enabled orgs by name; the caller's own org is marked. */
export function DuarOrgSelect({
  value,
  onValueChange,
  placeholder = "Choose an org",
  id,
}: {
  value: string | null;
  onValueChange: (orgId: string | null) => void;
  placeholder?: string;
  id?: string;
}) {
  const { data: orgs } = useOrgs();
  const { data: me } = useCurrentUser();
  const options = (orgs ?? []).map((o) => ({
    value: o.id,
    label: o.id === me?.org_id ? `${o.name} (your org)` : o.name,
  }));
  return (
    <SearchableSelect
      id={id}
      options={options}
      value={value}
      onValueChange={onValueChange}
      placeholder={placeholder}
      searchPlaceholder="Search orgs…"
      emptyMessage="No org by that name."
      clearable={false}
    />
  );
}
