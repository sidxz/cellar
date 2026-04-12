"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { TestTubes, Crosshair, Plus, Download } from "lucide-react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
import { ProtocolList } from "./protocol-list";
import { TargetList } from "./target-list";
import { CreateProtocolDialog } from "./create-protocol-dialog";
import { CreateTargetDialog } from "./create-target-dialog";
import { useVaultEnabled } from "../hooks/use-vault-enabled";
import { VaultImportDialog } from "./vault-import-dialog";

export function ScreeningDashboard() {
  const router = useRouter();
  const [tab, setTab] = useState("protocols");
  const [createProtocolOpen, setCreateProtocolOpen] = useState(false);
  const [createTargetOpen, setCreateTargetOpen] = useState(false);
  const [vaultImportOpen, setVaultImportOpen] = useState(false);
  const { enabled: vaultEnabled } = useVaultEnabled();

  return (
    <div>
      <PageHeader
        title="Assays"
        subtitle="Manage screening protocols and assay runs."
      />

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
            <div className="flex items-center gap-2">
              {vaultEnabled && (
                <Button variant="outline" onClick={() => setVaultImportOpen(true)}>
                  <Download className="mr-2 h-4 w-4" />
                  Import from Vault
                </Button>
              )}
              <Button onClick={() => setCreateProtocolOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                New Protocol
              </Button>
            </div>
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
              router.push(`/assays/protocols/${protocolId}`);
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
      <VaultImportDialog
        open={vaultImportOpen}
        onOpenChange={setVaultImportOpen}
        onImported={(protocolId) => {
          router.push(`/assays/protocols/${protocolId}`);
        }}
      />
    </div>
  );
}
