"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useApiVersion } from "@/shared/hooks/use-api-version";
import { useAppConfig } from "@/shared/lib/app-config";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

export function AboutDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { uiVersion, uiGitSha, uiBuildDate, environment } = useAppConfig();
  const api = useApiVersion(open);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>About Cellar</DialogTitle>
          <DialogDescription>Running build identity.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              UI
            </h3>
            <Row label="Version" value={`v${uiVersion}`} />
            <Row label="Commit" value={uiGitSha} />
            <Row label="Built" value={uiBuildDate} />
          </section>

          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              API
            </h3>
            {api.isLoading ? (
              <p className="text-xs text-muted-foreground">Loading…</p>
            ) : api.isError || !api.data ? (
              <p className="text-xs text-muted-foreground">API version unavailable</p>
            ) : (
              <>
                <Row label="Version" value={`v${api.data.version}`} />
                <Row label="Commit" value={api.data.git_sha} />
                <Row label="Built" value={api.data.build_date} />
              </>
            )}
          </section>

          <Row label="Environment" value={environment} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
