import { CollectionDetail } from "@/features/research-organization";

export default async function CollectionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CollectionDetail collectionId={id} />;
}
