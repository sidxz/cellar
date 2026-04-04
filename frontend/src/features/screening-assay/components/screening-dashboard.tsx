"use client";

import { useState } from "react";
import { TestTubes, Crosshair, Plus } from "lucide-react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { Button } from "@/shared/components/ui/button";
import { ProtocolList } from "./protocol-list";
import { TargetList } from "./target-list";
import { CreateProtocolDialog } from "./create-protocol-dialog";
import { CreateTargetDialog } from "./create-target-dialog";

export function ScreeningDashboard() {
  const [tab, setTab] = useState("protocols");
  const [createProtocolOpen, setCreateProtocolOpen] = useState(false);
  const [createTargetOpen, setCreateTargetOpen] = useState(false);

  return (
    <div>
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Assays</h1>
        <p className="mt-1 text-muted-foreground">
          Manage screening protocols and assay runs.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="protocols">
              <TestTubes className="mr-2 h-4 w-4" />
              Protocols
            </TabsTrigger>
            <TabsTrigger value="targets">
              <Crosshair className="mr-2 h-4 w-4" />
              Targets
            </TabsTrigger>
          </TabsList>

          {tab === "protocols" && (
            <Button onClick={() => setCreateProtocolOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New Protocol
            </Button>
          )}
          {tab === "targets" && (
            <Button onClick={() => setCreateTargetOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New Target
            </Button>
          )}
        </div>

        <TabsContent value="protocols" className="mt-4">
          <ProtocolList
            onSelect={(protocolId) => {
              window.location.href = `/assays/protocols/${protocolId}`;
            }}
          />
        </TabsContent>

        <TabsContent value="targets" className="mt-4">
          <TargetList />
        </TabsContent>
      </Tabs>

      <CreateProtocolDialog
        open={createProtocolOpen}
        onOpenChange={setCreateProtocolOpen}
      />
      <CreateTargetDialog
        open={createTargetOpen}
        onOpenChange={setCreateTargetOpen}
      />
    </div>
  );
}
