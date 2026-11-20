"use client";

import { SetupChecklist } from "@/features/workspace-config/components/setup-checklist";
import { PageHeader } from "@/shared/components/page-header";
import { ReturnToBarFromUrl } from "@/shared/components/return-to-bar";
import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { useAuthzHasRole } from "@duar-auth/nextjs";
import { ChevronDown, Download, FileSpreadsheet, Plus, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useCddEnabled } from "../hooks/use-cdd-enabled";
import type { Protocol } from "../types";
import { CddImportDialog } from "./cdd-import-dialog";
import { CreateProtocolDialog } from "./create-protocol-dialog";
import { CreateRunDialog } from "./create-run-dialog";
import { ProtocolBrowser } from "./protocol-browser";
import { ProtocolCsvImportDialog } from "./protocol-csv-import/protocol-csv-import-dialog";

export function ScreeningDashboard() {
  const router = useRouter();
  const [createProtocolOpen, setCreateProtocolOpen] = useState(false);
  const [cddImportOpen, setCddImportOpen] = useState(false);
  const [csvImportOpen, setCsvImportOpen] = useState(false);
  const [newFrom, setNewFrom] = useState<Protocol | null>(null);
  const canCreate = useAuthzHasRole("editor");
  const [createRunForProtocol, setCreateRunForProtocol] = useState<string | null>(null);
  const { enabled: cddEnabled } = useCddEnabled();

  return (
    <div className="space-y-3">
      <ReturnToBarFromUrl />
      <PageHeader title="Protocols" className="mb-3 flex-wrap gap-3">
        {(cddEnabled || canCreate) && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <Upload className="size-4" /> Import <ChevronDown className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {canCreate && (
                <DropdownMenuItem onSelect={() => setCsvImportOpen(true)}>
                  <FileSpreadsheet className="size-4" /> Import protocols (CSV)
                </DropdownMenuItem>
              )}
              {cddEnabled && (
                <DropdownMenuItem onSelect={() => setCddImportOpen(true)}>
                  <Download className="size-4" /> Import from CDD
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <Button variant="outline" size="sm" onClick={() => setCreateProtocolOpen(true)}>
          <Plus className="size-4" /> New protocol
        </Button>
      </PageHeader>
      <SetupChecklist compact />
      <ProtocolBrowser
        onNewFrom={canCreate ? setNewFrom : undefined}
        onSelect={(protocolId) => router.push(`/assays/protocols/${protocolId}`)}
      />

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
