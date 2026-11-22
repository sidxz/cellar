"use client";

import { DuarOrgSelect } from "@/shared/components/duar-org-select";
import { MemberSelector } from "@/shared/components/member-selector";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgName } from "@/shared/hooks/use-orgs";
import { useMemberNames, useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { useState } from "react";

/** Who disclosed the structures and for which Duar org; null = you / your org. */
export interface DiscloserChoice {
  userId: string | null;
  orgId: string | null;
}

/**
 * "Disclosed by: you · <your org>" in a registration form, with Change to name someone
 * else (picking them fills in their org) or another org. It is part of the form: the
 * form's own Register / Start button submits it.
 */
export function DiscloserPick({
  value,
  onChange,
}: {
  value: DiscloserChoice;
  onChange: (next: DiscloserChoice) => void;
}) {
  const { data: me } = useCurrentUser();
  const { data: members } = useWorkspaceMembers();
  const memberName = useMemberNames();
  const orgName = useOrgName();
  const [open, setOpen] = useState(false);
  const isDefault = !value.userId && !value.orgId;
  const person = value.userId && value.userId !== me?.user_id ? memberName(value.userId) : "You";
  const org = orgName(value.orgId ?? me?.org_id);

  return (
    <div className="grid gap-2">
      <Label>Disclosed by</Label>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span>
          {person} · {org || "your org"}
        </span>
        {!open && (
          <Button type="button" variant="link" size="sm" onClick={() => setOpen(true)}>
            Change
          </Button>
        )}
        {!isDefault && (
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => {
              onChange({ userId: null, orgId: null });
              setOpen(false);
            }}
          >
            Use me
          </Button>
        )}
      </div>
      {open && (
        <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">Person</p>
            <MemberSelector
              selectedId={value.userId}
              onSelect={(userId, member) =>
                onChange({
                  userId,
                  orgId:
                    member?.org_id ??
                    members?.find((m) => m.user_id === userId)?.org_id ??
                    value.orgId,
                })
              }
            />
          </div>
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">Org</p>
            <DuarOrgSelect
              value={value.orgId ?? me?.org_id ?? null}
              onValueChange={(orgId) => onChange({ ...value, orgId })}
            />
          </div>
        </div>
      )}
    </div>
  );
}
