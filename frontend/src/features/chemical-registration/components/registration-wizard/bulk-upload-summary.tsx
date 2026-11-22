"use client";

import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgName } from "@/shared/hooks/use-orgs";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { ProjectNames } from "./project-names";

export function BulkUploadSummary() {
  const input = useRegistrationWizard((state) => state.bulkInput);
  const { data: me } = useCurrentUser();
  const memberName = useMemberNames();
  const orgName = useOrgName();
  const { userId, orgId } = input.discloser;
  const person = userId && userId !== me?.user_id ? memberName(userId) : "You";
  return (
    <aside className="space-y-4" aria-label="Registration summary">
      <section className="rounded-lg border bg-muted/20 p-5">
        <h2 className="text-sm font-semibold">Registration summary</h2>
        <dl className="mt-4 space-y-4 text-sm">
          <div>
            <dt className="text-foreground/70">File</dt>
            <dd className="mt-1 break-all font-medium">{input.file?.name ?? "Choose a file"}</dd>
          </div>
          <div>
            <dt className="text-foreground/70">Disclosed by</dt>
            <dd className="mt-1 font-medium">
              {person} · {orgName(orgId ?? me?.org_id) || "your org"}
            </dd>
          </div>
          <div>
            <dt className="text-foreground/70">Projects</dt>
            <dd className="mt-1 font-medium">
              {input.projectIds.length ? (
                <ProjectNames ids={input.projectIds} />
              ) : (
                "No projects selected"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-foreground/70">Batch behavior</dt>
            <dd className="mt-1">
              Batch IDs in the file are used to create or match batches.
              {input.createBatchOnDuplicate
                ? " Existing compounds also get a new batch when no batch ID is supplied."
                : " Existing compounds do not get an extra batch when no batch ID is supplied."}
            </dd>
          </div>
        </dl>
        <p className="mt-4 border-t pt-4 text-sm text-foreground/70">
          You’ll review the expected results before starting registration.
        </p>
      </section>
      <details className="rounded-lg border p-5 text-sm">
        <summary className="cursor-pointer font-medium">File requirements</summary>
        <div className="mt-3 space-y-3 text-foreground/70">
          <p>Use CSV, XLSX, SDF, or SD. Spreadsheet files need a header row.</p>
          <p>Supply a compound name or structure. SDF records already include their structures.</p>
          <p>
            For multiple batches of a compound, repeat the compound details on separate rows and
            provide each batch’s full identifier.
          </p>
        </div>
      </details>
    </aside>
  );
}
