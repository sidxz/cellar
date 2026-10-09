"use client";

import { SetupChecklist } from "@/features/workspace-config/components/setup-checklist";
import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { useAuthzHasRole } from "@duar-auth/nextjs";
import { Crosshair, Download, Plus, Settings2, TestTubes, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useCddEnabled } from "../hooks/use-cdd-enabled";
import type { Protocol } from "../types";
import { CddImportDialog } from "./cdd-import-dialog";
import { CreateProtocolDialog } from "./create-protocol-dialog";
import { CreateRunDialog } from "./create-run-dialog";
import { ProtocolBrowser } from "./protocol-browser";
import { ProtocolCsvImportDialog } from "./protocol-csv-import/protocol-csv-import-dialog";
import { TargetList } from "./target-list";

export function ScreeningDashboard() {
  const router = useRouter();
  const [tab, setTab] = useState("protocols");
  const [createProtocolOpen, setCreateProtocolOpen] = useState(false);
  const [cddImportOpen, setCddImportOpen] = useState(false);
  const [csvImportOpen, setCsvImportOpen] = useState(false);
  const [newFrom, setNewFrom] = useState<Protocol | null>(null);
  const canCreate = useAuthzHasRole("editor");
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
              {canCreate && (
                <Button variant="outline" onClick={() => setCsvImportOpen(true)}>
                  <Upload className="mr-2 h-4 w-4" />
                  Import protocols (CSV)
                </Button>
              )}
              <Button onClick={() => setCreateProtocolOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                New Protocol
              </Button>
            </div>
          )}
          {tab === "targets" && (
            <Button asChild variant="outline">
              <Link href="/admin/targets">
                <Settings2 className="mr-2 h-4 w-4" />
                Manage targets
              </Link>
            </Button>
          )}
        </div>

        <TabsContent value="protocols" className="mt-4">
          <SetupChecklist />
          <ProtocolBrowser
            onNewFrom={canCreate ? setNewFrom : undefined}
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
      {newFrom && (
        <CreateProtocolDialog
          open
          onOpenChange={(o) => {
            if (!o) setNewFrom(null);
          }}
          prefill={newFrom}
          onLogRun={(protocolId) => setCreateRunForProtocol(protocolId)}
        />
      )}
      {createRunForProtocol && (
        <CreateRunDialog
          protocolId={createRunForProtocol}
          open={true}
          onOpenChange={(o) => {
            if (!o) setCreateRunForProtocol(null);
          }}
        />
      )}
      {csvImportOpen && <ProtocolCsvImportDialog open onOpenChange={setCsvImportOpen} />}
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
