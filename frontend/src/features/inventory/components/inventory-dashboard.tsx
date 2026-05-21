"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import { Boxes, Package, MapPin, Plus, Upload } from "lucide-react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { Button } from "@/shared/components/ui/button";
import { SearchInput } from "@/shared/components/search-input";
import { PageHeader } from "@/shared/components/page-header";
import { SummaryCards } from "./summary-cards";
import { GlobalBatchList } from "./batch-list";
import { GlobalSampleList } from "./sample-list";
import { StorageBrowser } from "./storage-browser";
import { CreateBatchDialog } from "./create-batch-dialog";
import { CreateSampleDialog } from "./create-sample-dialog";
import type { BatchGlobalParams } from "../hooks/use-batches";
import type { SampleGlobalParams } from "../hooks/use-samples";

export function InventoryDashboard() {
  const router = useRouter();
  const [tab, setTab] = useHashTab("batches");
  const [search, setSearch] = useState("");
  const [createBatchOpen, setCreateBatchOpen] = useState(false);
  const [createSampleOpen, setCreateSampleOpen] = useState(false);

  // Filter state driven by summary card clicks
  const [batchParams, setBatchParams] = useState<BatchGlobalParams>({});
  const [sampleParams, setSampleParams] = useState<SampleGlobalParams>({});

  const handleLowStockClick = useCallback(() => {
    setTab("samples");
    setSampleParams({ low_stock: true });
    setSearch("");
  }, []);

  const handleExpiringClick = useCallback(() => {
    setTab("batches");
    setBatchParams({ expiring_within_days: 30 });
    setSearch("");
  }, []);

  const handlePendingRequestsClick = useCallback(() => {
    router.push("/inventory/sample-requests?status=submitted,approved,preparing");
  }, [router]);

  // Sync search into active tab's params
  const activeBatchParams: BatchGlobalParams = {
    ...batchParams,
    search: tab === "batches" && search ? search : batchParams.search,
  };
  const activeSampleParams: SampleGlobalParams = {
    ...sampleParams,
    search: tab === "samples" && search ? search : sampleParams.search,
  };

  const clearFilters = () => {
    setSearch("");
    setBatchParams({});
    setSampleParams({});
  };

  return (
    <div>
      <PageHeader
        title="Inventory"
        subtitle="Manage batches, samples, and storage locations."
      >
        <Button variant="outline" asChild>
          <Link href="/inventory/batch-identifiers/import">
            <Upload className="mr-2 h-4 w-4" />
            Bulk import identifiers
          </Link>
        </Button>
        <Button variant="outline" onClick={() => setCreateBatchOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Batch
        </Button>
        <Button variant="outline" onClick={() => setCreateSampleOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Sample
        </Button>
      </PageHeader>

      {/* Summary cards */}
      <div className="mt-6">
        <SummaryCards
          onLowStockClick={handleLowStockClick}
          onExpiringClick={handleExpiringClick}
          onPendingRequestsClick={handlePendingRequestsClick}
        />
      </div>

      {/* Search bar */}
      <SearchInput
        value={search}
        onChange={(v) => {
          setSearch(v);
          // Clear card-driven filters when user types
          if (tab === "batches") setBatchParams({});
          if (tab === "samples") setSampleParams({});
        }}
        placeholder="Search batches, samples, compounds..."
        className="mt-6"
      />

      {/* Tabs */}
      <Tabs value={tab} onValueChange={(t) => { setTab(t); clearFilters(); }} className="mt-4">
        <TabsList>
          <TabsTrigger value="batches">
            <Boxes className="mr-2 h-4 w-4" />
            Batches
          </TabsTrigger>
          <TabsTrigger value="samples">
            <Package className="mr-2 h-4 w-4" />
            Samples
          </TabsTrigger>
          <TabsTrigger value="storage">
            <MapPin className="mr-2 h-4 w-4" />
            Storage
          </TabsTrigger>
        </TabsList>

        <TabsContent value="batches" className="mt-4">
          <GlobalBatchList params={activeBatchParams} />
        </TabsContent>

        <TabsContent value="samples" className="mt-4">
          <GlobalSampleList params={activeSampleParams} />
        </TabsContent>

        <TabsContent value="storage" className="mt-4">
          <StorageBrowser />
        </TabsContent>
      </Tabs>

      <CreateBatchDialog
        open={createBatchOpen}
        onOpenChange={setCreateBatchOpen}
      />
      <CreateSampleDialog
        open={createSampleOpen}
        onOpenChange={setCreateSampleOpen}
      />
    </div>
  );
}
