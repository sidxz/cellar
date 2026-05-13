import { CampaignList } from "@/features/screen-campaign/components/campaign-list";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function CampaignsPage({ params }: PageProps) {
  const { id: projectId } = await params;
  return (
    <div className="container py-6">
      <h1 className="mb-6 text-2xl font-semibold">Campaigns</h1>
      <CampaignList projectId={projectId} />
    </div>
  );
}
