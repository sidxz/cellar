"use client";

import { useState } from "react";

import { useCollection } from "@/features/research-organization/hooks/use-collections";
import { useCommitCollectionImport } from "@/features/research-organization/hooks/use-commit-collection-import";
import {
  useCollectionImportTemplates,
  useCreateCollectionImportTemplate,
} from "@/features/research-organization/hooks/use-collection-import-templates";
import { usePreviewCollectionImport } from "@/features/research-organization/hooks/use-preview-collection-import";
import { useBreadcrumbOverride } from "@/shared/components/layout/breadcrumb-context";
import type {
  BulkAddRequestBody,
  BulkAddResponse,
  BulkAddRowBody,
} from "@/shared/lib/api/model";

import { ConfirmStep } from "./confirm-step";
import { MappingStep } from "./mapping-step";
import { PreviewStep, type PreviewResult } from "./preview-step";
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

export function CollectionImportWizard({ collectionId }: { collectionId: string }) {
  const [step, setStep] = useState<Step>("upload");
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [pendingTemplateName, setPendingTemplateName] = useState<string | null>(
    null,
  );

  const templatesQ = useCollectionImportTemplates();
  const createTpl = useCreateCollectionImportTemplate();
  const previewMut = usePreviewCollectionImport(collectionId);
  const commitMut = useCommitCollectionImport(collectionId);

  const collectionQuery = useCollection(collectionId);
  const collectionName = collectionQuery.data?.name ?? "";
  useBreadcrumbOverride(collectionId, collectionName);

  function buildBody(currentMapping: Record<string, string>): BulkAddRequestBody {
    return {
      rows: rows.map((r, i): BulkAddRowBody => {
        const out: BulkAddRowBody = { row_index: i };
        for (const [role, header] of Object.entries(currentMapping)) {
          if (!isRowField(role)) continue;
          const v = r[header];
          out[role] = v ? v : null;
        }
        return out;
      }),
    };
  }

  async function handleContinueFromMapping(out: {
    mapping: Record<string, string>;
    saveAsTemplate?: { name: string };
  }) {
    setMapping(out.mapping);
    if (out.saveAsTemplate) setPendingTemplateName(out.saveAsTemplate.name);
    const res = await previewMut.mutateAsync(buildBody(out.mapping));
    setPreview(toPreviewResult(res));
    setStep("preview");
  }

  async function handleCommit() {
    const res = await commitMut.mutateAsync(buildBody(mapping));
    setPreview(toPreviewResult(res));
    if (pendingTemplateName) {
      await createTpl.mutateAsync({
        name: pendingTemplateName,
        column_mapping: mapping,
      });
    }
    setStep("confirm");
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-2xl font-semibold">
        Bulk import to{" "}
        {collectionName ? (
          <span className="text-primary">{collectionName}</span>
        ) : (
          "collection"
        )}
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
          onContinue={handleContinueFromMapping}
          submitting={previewMut.isPending}
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
            setPreview(null);
          }}
        />
      )}
    </div>
  );
}
