import { MergePreviewPage } from "@/features/chemical-registration/components/merge-preview-page";

export default async function MergePreview({
  params,
}: {
  params: Promise<{ id: string; disclosureId: string }>;
}) {
  const { id, disclosureId } = await params;
  return <MergePreviewPage compoundId={id} disclosureId={disclosureId} />;
}
