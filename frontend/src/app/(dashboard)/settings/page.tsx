"use client";

import { useTheme } from "next-themes";

import { HexLensLogo } from "@/shared/components/hex-lens-logo";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { useApiVersion } from "@/shared/hooks/use-api-version";
import { useAppConfig } from "@/shared/lib/app-config";
import { type FontFamily, useFontFamilyStore } from "@/shared/lib/stores/font-family-store";
import { usePreferencesStore } from "@/shared/lib/stores/preferences-store";

const FONTS: { value: FontFamily; label: string }[] = [
  { value: "plex", label: "IBM Plex" },
  { value: "inter", label: "Inter" },
];

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

function VersionRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

export default function SettingsPage() {
  const { resolvedTheme, setTheme: setNextTheme } = useTheme();
  const setStoreTheme = usePreferencesStore((s) => s.setTheme);
  const font = useFontFamilyStore((s) => s.font);
  const setFont = useFontFamilyStore((s) => s.setFont);
  const { uiVersion, uiGitSha, uiBuildDate, environment } = useAppConfig();
  const api = useApiVersion(true);

  // Same dual-write as ThemeToggle: next-themes drives the DOM, the
  // preferences store keeps its mirror.
  const setTheme = (theme: "light" | "dark") => {
    setNextTheme(theme);
    setStoreTheme(theme);
  };

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 p-6">
      <h1 className="text-lg font-semibold">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Per-user preferences, stored in this browser.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm">Theme</span>
            <div className="flex gap-1">
              {THEMES.map((t) => (
                <Button
                  key={t.value}
                  variant={resolvedTheme === t.value ? "secondary" : "ghost"}
                  size="sm"
                  aria-pressed={resolvedTheme === t.value}
                  onClick={() => setTheme(t.value)}
                >
                  {t.label}
                </Button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm">Font</span>
            <div className="flex gap-1">
              {FONTS.map((f) => (
                <Button
                  key={f.value}
                  variant={font === f.value ? "secondary" : "ghost"}
                  size="sm"
                  aria-pressed={font === f.value}
                  onClick={() => setFont(f.value)}
                >
                  {f.label}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <HexLensLogo className="size-5" />
            <CardTitle>About Cellar</CardTitle>
          </div>
          <CardDescription>Running build identity.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              UI
            </h3>
            <VersionRow label="Version" value={`v${uiVersion}`} />
            <VersionRow label="Commit" value={uiGitSha} />
            <VersionRow label="Built" value={uiBuildDate} />
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
                <VersionRow label="Version" value={`v${api.data.version}`} />
                <VersionRow label="Commit" value={api.data.git_sha} />
                <VersionRow label="Built" value={api.data.build_date} />
              </>
            )}
          </section>
          <VersionRow label="Environment" value={environment} />
        </CardContent>
      </Card>
    </div>
  );
}
