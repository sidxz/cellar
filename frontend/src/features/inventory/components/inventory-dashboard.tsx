"use client";

import { useState } from "react";
import { Package, Boxes, MapPin } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { BatchList } from "./batch-list";
import { SampleList } from "./sample-list";
import { StorageBrowser } from "./storage-browser";

export function InventoryDashboard() {
  const [tab, setTab] = useState("batches");

  return (
    <div>
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Inventory</h1>
        <p className="mt-1 text-muted-foreground">
          Manage batches, samples, and storage locations.
        </p>
      </div>

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

        <TabsContent value="batches" className="mt-4">
          <BatchList />
        </TabsContent>
        <TabsContent value="samples" className="mt-4">
          <SampleList />
        </TabsContent>
        <TabsContent value="storage" className="mt-4">
          <StorageBrowser />
        </TabsContent>
      </Tabs>
    </div>
  );
}
