"use client";

import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Crosshair, Download, Plus, TestTubes } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useCddEnabled } from "../hooks/use-cdd-enabled";
import { CddImportDialog } from "./cdd-import-dialog";
import { CreateProtocolDialog } from "./create-protocol-dialog";
import { CreateRunDialog } from "./create-run-dialog";
import { CreateTargetDialog } from "./create-target-dialog";
import { ProtocolBrowser } from "./protocol-browser";
import { TargetList } from "./target-list";

export function ScreeningDashboard() {
  const router = useRouter();
  const [tab, setTab] = useState("protocols");
  const [createProtocolOpen, setCreateProtocolOpen] = useState(false);
  const [createTargetOpen, setCreateTargetOpen] = useState(false);
  const [cddImportOpen, setCddImportOpen] = useState(false);
  const [createRunForProtocol, setCreateRunForProtocol] = useState<string | null>(null);
  const { enabled: cddEnabled } = useCddEnabled();

  return (
    <div>
      <PageHeader title="Assays" subtitle="Manage screening protocols and assay runs." />

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
              {cddEnabled && (
                <Button variant="outline" onClick={() => setCddImportOpen(true)}>
                  <Download className="mr-2 h-4 w-4" />
                  Import from CDD
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
          <ProtocolBrowser
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
        onLogRun={(protocolId) => setCreateRunForProtocol(protocolId)}
      />
      {createRunForProtocol && (
        <CreateRunDialog
          protocolId={createRunForProtocol}
          open={true}
          onOpenChange={(o) => {
            if (!o) setCreateRunForProtocol(null);
          }}
        />
      )}
      <CreateTargetDialog open={createTargetOpen} onOpenChange={setCreateTargetOpen} />
      <CddImportDialog
        open={cddImportOpen}
        onOpenChange={setCddImportOpen}
        onImported={(protocolId) => {
          router.push(`/assays/protocols/${protocolId}`);
        }}
      />
    </div>
  );
}
