import { CollectionImportWizard } from "@/features/research-organization/components/collection-import-wizard";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CollectionImportWizard collectionId={id} />;
}
