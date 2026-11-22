"use client";

import { useAuditByEntity } from "@/features/audit/hooks/use-audit";
import type { AuditOperation } from "@/features/audit/types";
import { DuarOrgSelect } from "@/shared/components/duar-org-select";
import { MemberSelector } from "@/shared/components/member-selector";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgName } from "@/shared/hooks/use-orgs";
import { useMemberNames, useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { formatDate, formatDateTime } from "@/shared/lib/format-date";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useChangeDiscloser } from "../../hooks/use-change-discloser";
import type { Molecule } from "../../types";

const DISCLOSER_FIELDS = new Set(["disclosed_by", "disclosed_by_org_id"]);

/**
 * Who registered the compound and who disclosed it, each with their Duar org.
 * An admin or the registrant can correct the discloser (explicit Save); every
 * correction is listed from History.
 */
export function DisclosureTab({ molecule }: { molecule: Molecule }) {
  const { data: me } = useCurrentUser();
  const canChange =
    !!me &&
    me.workspace_role !== "viewer" &&
    (me.is_admin || (!!molecule.registered_by && me.user_id === molecule.registered_by));
  return (
    <div className="space-y-6">
      <DisclosedByCard molecule={molecule} canChange={canChange} />
      <RegisteredByCard molecule={molecule} />
      <DiscloserChanges moleculeId={molecule.id} />
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="font-medium">{children || "—"}</p>
    </div>
  );
}

function FactsCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id}>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle id={id}>{title}</CardTitle>
          {action}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </section>
  );
}

function DisclosedByCard({ molecule, canChange }: { molecule: Molecule; canChange: boolean }) {
  const router = useRouter();
  const memberName = useMemberNames();
  const orgName = useOrgName();
  const [editing, setEditing] = useState(false);

  if (molecule.structure_status !== "disclosed") {
    return (
      <FactsCard title="Disclosed by">
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">Not disclosed yet.</p>
          <Button
            size="sm"
            onClick={() => router.push(`/compounds/register?disclose=${molecule.id}`)}
          >
            Disclose structure
          </Button>
        </div>
      </FactsCard>
    );
  }

  return (
    <FactsCard
      title="Disclosed by"
      action={
        canChange && !editing ? (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            Change
          </Button>
        ) : null
      }
    >
      {editing ? (
        <DiscloserEditor molecule={molecule} onDone={() => setEditing(false)} />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Fact label="Person">{memberName(molecule.disclosed_by)}</Fact>
          <Fact label="Org">{orgName(molecule.disclosed_by_org_id)}</Fact>
          <Fact label="When">{formatDateTime(molecule.disclosed_at)}</Fact>
          <Fact label="Declared disclosure date">
            {molecule.disclosure_date ? formatDate(molecule.disclosure_date) : ""}
          </Fact>
        </div>
      )}
    </FactsCard>
  );
}

function DiscloserEditor({ molecule, onDone }: { molecule: Molecule; onDone: () => void }) {
  const { data: members } = useWorkspaceMembers();
  const change = useChangeDiscloser(molecule.id);
  const [person, setPerson] = useState<string | null>(molecule.disclosed_by ?? null);
  const [org, setOrg] = useState<string | null>(molecule.disclosed_by_org_id ?? null);
  const dirty =
    person !== (molecule.disclosed_by ?? null) || org !== (molecule.disclosed_by_org_id ?? null);

  const pickPerson = (userId: string | null) => {
    setPerson(userId);
    const memberOrg = members?.find((m) => m.user_id === userId)?.org_id;
    if (memberOrg) setOrg(memberOrg);
  };
  const save = () => {
    if (!person) return;
    change.mutate({ disclosed_by: person, disclosed_by_org_id: org }, { onSuccess: onDone });
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">Person</p>
          <MemberSelector selectedId={person} onSelect={pickPerson} />
        </div>
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">Org</p>
          <DuarOrgSelect value={org} onValueChange={setOrg} />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onDone} disabled={change.isPending}>
          Cancel
        </Button>
        <Button size="sm" onClick={save} disabled={change.isPending || !person || !dirty}>
          {change.isPending ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}

function RegisteredByCard({ molecule }: { molecule: Molecule }) {
  const memberName = useMemberNames();
  const orgName = useOrgName();
  return (
    <FactsCard title="Registered by">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Fact label="Person">
          {molecule.registered_by ? memberName(molecule.registered_by) : "Not on file"}
        </Fact>
        <Fact label="Org">{orgName(molecule.registered_by_org_id)}</Fact>
        <Fact label="When">{formatDateTime(molecule.created_at)}</Fact>
        {molecule.scientist_name && <Fact label="Scientist">{molecule.scientist_name}</Fact>}
      </div>
    </FactsCard>
  );
}

function DiscloserChanges({ moleculeId }: { moleculeId: string }) {
  const { data: ops } = useAuditByEntity("Molecule", moleculeId);
  const memberName = useMemberNames();
  const orgName = useOrgName();
  const changes = (ops ?? []).flatMap((op: AuditOperation) =>
    op.entries.filter((e) => DISCLOSER_FIELDS.has(e.field_name)).map((e) => ({ op, entry: e })),
  );
  if (changes.length === 0) return null;
  const label = (field: string, value: string | null) =>
    (field === "disclosed_by" ? memberName(value) : orgName(value)) || "nobody";
  return (
    <div className="space-y-2">
      <h3 id="discloser-changes" className="text-sm font-medium text-muted-foreground">
        Changes to the discloser
      </h3>
      <ul aria-labelledby="discloser-changes" className="space-y-1 text-sm">
        {changes.map(({ op, entry }) => (
          <li key={`${op.id}-${entry.field_name}`}>
            {formatDate(op.performed_at)} · {memberName(op.performed_by)} changed the{" "}
            {entry.field_name === "disclosed_by" ? "person" : "org"} from{" "}
            {label(entry.field_name, entry.old_value)} to {label(entry.field_name, entry.new_value)}
          </li>
        ))}
      </ul>
    </div>
  );
}
