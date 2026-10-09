"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { useAuthzHasRole } from "@duar-auth/nextjs";
import Link from "next/link";
import { useState } from "react";
import { useSeedDefaultProtocolCategories } from "../hooks/use-protocol-categories";
import { useWorkspaceSetup } from "../hooks/use-workspace-setup";

const DISMISSED_KEY = "cellar:setup-checklist-dismissed";

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

/** What an admin still has to configure before protocol work runs smoothly. Admins only;
 *  gone once everything is done; "Dismiss" hides it for this viewer. */
export function SetupChecklist() {
  const isAdmin = useAuthzHasRole("admin");
  const { data } = useWorkspaceSetup(isAdmin);
  const seed = useSeedDefaultProtocolCategories();
  const [dismissed, setDismissed] = useState(readDismissed);

  if (!isAdmin || !data || dismissed) return null;

  const newCategories = data.missing_default_categories.length;
  const items: {
    key: string;
    text: string;
    link: string;
    label: string;
    action?: React.ReactNode;
  }[] = [];
  if (newCategories > 0)
    items.push({
      key: "categories",
      text: `${newCategories} shipped ${newCategories === 1 ? "category is" : "categories are"} not in this workspace.`,
      link: "/admin/protocol-categories",
      label: "Categories",
      action: (
        <Button size="sm" disabled={seed.isPending} onClick={() => seed.mutate()}>
          {`Add ${newCategories} new shipped ${newCategories === 1 ? "category" : "categories"}`}
        </Button>
      ),
    });
  if (data.missing_default_forms > 0)
    items.push({
      key: "forms",
      text: `${data.missing_default_forms} shipped ${data.missing_default_forms === 1 ? "form is" : "forms are"} missing from your categories.`,
      link: "/admin/protocol-forms",
      label: "Forms",
    });
  if (!data.bioportal_key)
    items.push({
      key: "key",
      text: "No BioPortal API key, so ontology search is unavailable.",
      link: "/admin/api-keys",
      label: "API keys",
    });
  if (data.home_organisms === 0)
    items.push({
      key: "home",
      text: "No home organism set, so protocol names spell out every organism.",
      link: "/admin/settings",
      label: "Home organism",
    });
  if (data.targets === 0)
    items.push({
      key: "targets",
      text: "No targets yet. Sync them from the target registry.",
      link: "/admin/targets",
      label: "Targets",
    });
  if (items.length === 0) return null;

  const dismiss = () => {
    setDismissed(true);
    try {
      window.localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      // storage unavailable: hidden for this visit only
    }
  };

  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Finish setting up protocols</CardTitle>
        <Button variant="ghost" size="sm" onClick={dismiss}>
          Dismiss
        </Button>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {items.map((i) => (
            <li key={i.key} className="flex items-center justify-between gap-3 text-sm">
              <span>{i.text}</span>
              <span className="flex shrink-0 items-center gap-2">
                {i.action}
                <Button asChild variant="outline" size="sm">
                  <Link href={i.link}>{i.label}</Link>
                </Button>
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
