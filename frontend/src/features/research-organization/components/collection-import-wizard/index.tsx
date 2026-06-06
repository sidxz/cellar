"use client";

import { useAuthz } from "@sentinel-auth/nextjs";
import { useState } from "react";

import {
  useCollectionImportTemplates,
  useCreateCollectionImportTemplate,
} from "@/features/research-organization/hooks/use-collection-import-templates";
import { useCollection } from "@/features/research-organization/hooks/use-collections";
import { useCommitCollectionImport } from "@/features/research-organization/hooks/use-commit-collection-import";
import { usePreviewCollectionImport } from "@/features/research-organization/hooks/use-preview-collection-import";
import type { BulkAddRequestBody, BulkAddResponse, BulkAddRowBody } from "@/shared/lib/api/model";
import { useBreadcrumbOverride } from "@/shared/lib/stores/breadcrumb-store";
import { showSuccess } from "@/shared/lib/toast";

import { ConfirmStep } from "./confirm-step";
import { MappingStep } from "./mapping-step";
import { type PreviewResult, PreviewStep } from "./preview-step";
import { UploadStep } from "./upload-step";

type Step = "upload" | "mapping" | "preview" | "confirm";

// The roles the mapping step emits — these are the keys of BulkAddRowBody
// minus row_index.
const ROW_FIELDS = [
  "registration_number",
  "external_id",
  "inchi_key",
  "smiles",
  "name",
  "notes",
] as const;
type RowField = (typeof ROW_FIELDS)[number];

function isRowField(s: string): s is RowField {
  return (ROW_FIELDS as readonly string[]).includes(s);
}

// Cast BulkAddResponse → PreviewResult shape used by the preview/confirm steps.
// The generated type uses `BulkAddResponsePreviewId` (string | null | undefined)
// for `preview_id`; the local PreviewResult interface uses `string | null`. The
// outcome shape is structurally compatible.
function toPreviewResult(res: BulkAddResponse): PreviewResult {
  return res as unknown as PreviewResult;
}

// Human-readable message for a failed template save. A workspace-unique name
// collision is the common case (the BE has a unique (workspace, name)
// constraint), so call it out explicitly; otherwise fall back to the raw error.
function templateSaveErrorMessage(err: unknown, name: string): string {
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 409 || status === 400) {
    return `Couldn't save template "${name}" — a template with that name may already exist. Rename it or uncheck "Save this mapping".`;
  }
  const msg = err instanceof Error ? err.message : String(err);
  return `Couldn't save template "${name}": ${msg}`;
}

export function CollectionImportWizard({ collectionId }: { collectionId: string }) {
  const [step, setStep] = useState<Step>("upload");
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);
  // Id of a template just saved from this wizard — signals the mapping step to
  // clear its "save as template" toggle so the just-saved name doesn't trip the
  // duplicate-name guard against itself.
  const [justSavedTemplateId, setJustSavedTemplateId] = useState<string | null>(null);

  const { user } = useAuthz();
  const currentUserId = user?.userId;

  const templatesQ = useCollectionImportTemplates(collectionId);
  const createTpl = useCreateCollectionImportTemplate();
  const previewMut = usePreviewCollectionImport(collectionId);
  const commitMut = useCommitCollectionImport(collectionId);

  const collectionQuery = useCollection(collectionId);
  const collectionName = collectionQuery.data?.name ?? "";
  useBreadcrumbOverride(collectionId, collectionName);

  function buildRows(currentMapping: Record<string, string>): BulkAddRowBody[] {
    return rows.map((r, i): BulkAddRowBody => {
      const out: BulkAddRowBody = { row_index: i };
      for (const [role, header] of Object.entries(currentMapping)) {
        if (!isRowField(role)) continue;
        const v = r[header];
        out[role] = v ? v : null;
      }
      return out;
    });
  }

  function buildPreviewBody(currentMapping: Record<string, string>): BulkAddRequestBody {
    // Preview body never carries a preview_id — BE mints a fresh one.
    return {
      rows: buildRows(currentMapping),
      template_id: selectedTemplateId,
    };
  }

  function buildCommitBody(): BulkAddRequestBody {
    // Commit body forwards the preview_id stashed from the prior preview
    // call so the BE can reuse cached outcomes (skip the resolver). If
    // previewId is null (e.g. the preview call failed to mint one), the
    // BE silently falls back to the full resolve path.
    return {
      rows: buildRows(mapping),
      template_id: selectedTemplateId,
      preview_id: previewId,
    };
  }

  async function handleContinueFromMapping(out: {
    mapping: Record<string, string>;
    saveAsTemplate?: { name: string };
  }) {
    setMapping(out.mapping);
    setTemplateError(null);

    // Save the template NOW — when the chemist finalizes the mapping — not
    // after the molecules commit. The mapping is a reusable artifact in its own
    // right; coupling it to a successful import is what made saves silently
    // vanish. On failure we surface the error and stay on the mapping step so
    // the chemist can fix the name (or uncheck save) rather than lose it.
    if (out.saveAsTemplate) {
      try {
        const created = await createTpl.mutateAsync({
          name: out.saveAsTemplate.name,
          column_mapping: out.mapping,
        });
        // Treat the just-saved template as the applied one so commit records
        // usage against it (used_in_this_collection).
        setSelectedTemplateId(created.id);
        setJustSavedTemplateId(created.id);
        showSuccess(`Template "${created.name}" saved`);
      } catch (e) {
        setTemplateError(templateSaveErrorMessage(e, out.saveAsTemplate.name));
        return; // stay on mapping; nothing imported yet
      }
    }

    const res = await previewMut.mutateAsync(buildPreviewBody(out.mapping));
    setPreview(toPreviewResult(res));
    setPreviewId(res.preview_id ?? null);
    setStep("preview");
  }

  async function handleCommit() {
    const res = await commitMut.mutateAsync(buildCommitBody());
    setPreview(toPreviewResult(res));
    setStep("confirm");
  }

  // Re-run the resolution over the SAME uploaded rows (still in client state).
  // Used after the chemist registers the unregistered molecules in a separate
  // tab: re-checking picks them up so the whole set resolves and can be added.
  async function handleRecheck() {
    const res = await previewMut.mutateAsync(buildPreviewBody(mapping));
    setPreview(toPreviewResult(res));
    setPreviewId(res.preview_id ?? null);
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-2xl font-semibold">
        Bulk import to{" "}
        {collectionName ? <span className="text-primary">{collectionName}</span> : "collection"}
      </h1>
      {step === "upload" && (
        <UploadStep
          onParsed={({ headers, rows }) => {
            setHeaders(headers);
            setRows(rows);
            setStep("mapping");
          }}
        />
      )}
      {step === "mapping" && (
        <MappingStep
          headers={headers}
          rows={rows}
          templates={templatesQ.data ?? []}
          currentUserId={currentUserId}
          selectedTemplateId={selectedTemplateId}
          onSelectedTemplateChange={setSelectedTemplateId}
          onContinue={handleContinueFromMapping}
          submitting={previewMut.isPending || createTpl.isPending}
          templateError={templateError}
          justSavedTemplateId={justSavedTemplateId}
        />
      )}
      {step === "preview" && preview && (
        <PreviewStep
          result={preview}
          collectionId={collectionId}
          onCommit={handleCommit}
          rows={rows}
          mapping={mapping}
          submitting={commitMut.isPending}
          onRecheck={handleRecheck}
          rechecking={previewMut.isPending}
        />
      )}
      {step === "confirm" && preview && (
        <ConfirmStep
          result={preview}
          collectionId={collectionId}
          onClose={() => {
            setStep("upload");
            setHeaders([]);
            setRows([]);
            setMapping({});
            setSelectedTemplateId(null);
            setPreview(null);
            setPreviewId(null);
          }}
        />
      )}
    </div>
  );
}
