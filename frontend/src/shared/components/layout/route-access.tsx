"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { useAllowsRole } from "@/shared/hooks/use-allows-role";
import { activeNavItem, navigation } from "@/shared/lib/navigation";
import { Lock } from "lucide-react";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/** Renders the page only for users holding the role its nav entry `requires`,
 * so opening an admin URL directly shows a notice instead of a page whose
 * actions the backend would refuse. The backend still enforces every call. */
export function RouteAccess({ children }: { children: ReactNode }) {
  const required = activeNavItem(navigation, usePathname())?.requires;
  const allows = useAllowsRole();
  if (required && !allows(required)) {
    return (
      <EmptyState
        icon={Lock}
        title="You don't have access to this page"
        description={`It needs the ${required} role in this workspace. Ask a workspace admin if you need it.`}
      />
    );
  }
  return children;
}
