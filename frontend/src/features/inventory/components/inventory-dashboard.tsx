"use client";

import { useState } from "react";
import { Package, Boxes, MapPin, Plus } from "lucide-react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
import { BatchList } from "./batch-list";
import { SampleList } from "./sample-list";
import { StorageBrowser } from "./storage-browser";
import { CreateBatchDialog } from "./create-batch-dialog";
import { CreateSampleDialog } from "./create-sample-dialog";
import { CreateStorageLocationDialog } from "./create-storage-location-dialog";
import { MoleculeSelector } from "./molecule-selector";
import { BatchSelector } from "./batch-selector";

export function InventoryDashboard() {
  const [tab, setTab] = useState("batches");
  const [selectedMoleculeId, setSelectedMoleculeId] = useState<string | null>(
    null
  );
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [createBatchOpen, setCreateBatchOpen] = useState(false);
  const [createSampleOpen, setCreateSampleOpen] = useState(false);
  const [createStorageOpen, setCreateStorageOpen] = useState(false);

  return (
    <div>
      <PageHeader
        title="Inventory"
        subtitle="Manage batches, samples, and storage locations."
      />

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
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

        <TabsContent value="batches" className="mt-4 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <MoleculeSelector
              selectedId={selectedMoleculeId}
              onSelect={(id) => {
                setSelectedMoleculeId(id);
                setSelectedBatchId(null);
              }}
            />
            {selectedMoleculeId && (
              <Button onClick={() => setCreateBatchOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Batch
              </Button>
            )}
          </div>
          <BatchList
            moleculeId={selectedMoleculeId ?? undefined}
            onSelectBatch={setSelectedBatchId}
          />
        </TabsContent>

        <TabsContent value="samples" className="mt-4 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <MoleculeSelector
                selectedId={selectedMoleculeId}
                onSelect={(id) => {
                  setSelectedMoleculeId(id);
                  setSelectedBatchId(null);
                }}
              />
              {selectedMoleculeId && (
                <BatchSelector
                  moleculeId={selectedMoleculeId}
                  selectedId={selectedBatchId}
                  onSelect={setSelectedBatchId}
                />
              )}
            </div>
            {selectedBatchId && (
              <Button onClick={() => setCreateSampleOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Sample
              </Button>
            )}
          </div>
          <SampleList batchId={selectedBatchId ?? undefined} />
        </TabsContent>

        <TabsContent value="storage" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <Button onClick={() => setCreateStorageOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Location
            </Button>
          </div>
          <StorageBrowser />
        </TabsContent>
      </Tabs>

      {selectedMoleculeId && (
        <CreateBatchDialog
          moleculeId={selectedMoleculeId}
          open={createBatchOpen}
          onOpenChange={setCreateBatchOpen}
        />
      )}
      {selectedBatchId && (
        <CreateSampleDialog
          batchId={selectedBatchId}
          open={createSampleOpen}
          onOpenChange={setCreateSampleOpen}
        />
      )}
      <CreateStorageLocationDialog
        open={createStorageOpen}
        onOpenChange={setCreateStorageOpen}
      />
    </div>
  );
}
