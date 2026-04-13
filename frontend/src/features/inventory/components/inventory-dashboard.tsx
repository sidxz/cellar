"use client";

import { useState, useCallback } from "react";
import { Boxes, Package, MapPin, Plus, Search } from "lucide-react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
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
  const [tab, setTab] = useState("batches");
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
    window.location.href = "/inventory/sample-requests?status=submitted,approved,preparing";
  }, []);

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
      <div className="relative mt-6">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search batches, samples, compounds..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            // Clear card-driven filters when user types
            if (tab === "batches") setBatchParams({});
            if (tab === "samples") setSampleParams({});
          }}
          className="pl-10"
        />
      </div>

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
