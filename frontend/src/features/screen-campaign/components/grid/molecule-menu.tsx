"use client";

/**
 * What a chemist does with a row's compound from the results grid: open it, search for
 * compounds like it, or copy its SMILES, ID or alias. Right-click the Structure or Compound cell
 * for these; the row's "⋯" button offers them too, with the note's actions, for the keyboard.
 */

import { Copy, ExternalLink, MoreHorizontal, ScanSearch, Search } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/shared/components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import type { MoleculeResponse } from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";
import { cn, shortId } from "@/shared/lib/utils";

type Molecule = Pick<
  MoleculeResponse,
  "registration_number" | "name" | "structure" | "identifiers"
>;

export type Shortcut = { label: string; icon: ReactNode } & (
  | { href: string }
  | { copy: string; what: string }
  | { run: () => void }
);

/** A compound's other identifiers: neither its name nor its registration number, vault ids
 *  marked "(CDD)". */
export function aliasesOf(m: Molecule | undefined): string[] {
  return (m?.identifiers ?? [])
    .filter(
      (i) => !!i.identifier && i.identifier !== m?.name && i.identifier !== m?.registration_number,
    )
    .map((i) => (i.identifier_type === "cdd_molecule_id" ? `${i.identifier} (CDD)` : i.identifier));
}

/** Open, then find similar / substructure (only with a structure), then the copies. The search
 *  link names the molecule by id, never by structure. */
export function moleculeShortcuts(moleculeId: string, m: Molecule | undefined): Shortcut[][] {
  const smiles = m?.structure?.smiles;
  const search = (mode: "similar" | "substructure") =>
    `/search?${new URLSearchParams({ molecule_id: moleculeId, mode })}`;
  const alias = m?.name && m.name !== m.registration_number ? m.name : null;
  const open: Shortcut[] = [
    { label: "Open compound", icon: <ExternalLink />, href: `/compounds/${moleculeId}` },
    ...(smiles
      ? [
          { label: "Find similar", icon: <Search />, href: search("similar") },
          { label: "Find substructure", icon: <ScanSearch />, href: search("substructure") },
        ]
      : []),
  ];
  const copies: Shortcut[] = [
    ...(smiles ? [{ label: "Copy SMILES", icon: <Copy />, copy: smiles, what: "SMILES" }] : []),
    ...(m?.registration_number
      ? [{ label: "Copy ID", icon: <Copy />, copy: m.registration_number, what: "ID" }]
      : []),
    ...(alias ? [{ label: "Copy alias", icon: <Copy />, copy: alias, what: "Alias" }] : []),
  ];
  return [open, copies].filter((g) => g.length > 0);
}

async function copy(value: string, what: string) {
  // Inside the try: outside a secure context navigator.clipboard is undefined and throws.
  try {
    await navigator.clipboard.writeText(value);
    showSuccess(`${what} copied`);
  } catch {
    showError(`Could not copy the ${what.toLowerCase()}`);
  }
}

const act = (s: Shortcut) => () => {
  if ("copy" in s) void copy(s.copy, s.what);
  else if ("run" in s) s.run();
};

/** Right-click anywhere in ``children`` for the compound's shortcuts. */
export function MoleculeContextMenu({
  moleculeId,
  molecule,
  children,
}: {
  moleculeId: string;
  molecule: Molecule | undefined;
  children: ReactNode;
}) {
  const groups = moleculeShortcuts(moleculeId, molecule);
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent>
        {groups.map((group, i) => [
          i > 0 && <ContextMenuSeparator key={`sep-${group[0]?.label}`} />,
          ...group.map((s) =>
            "href" in s ? (
              <ContextMenuItem key={s.label} asChild>
                <Link href={s.href}>
                  {s.icon}
                  {s.label}
                </Link>
              </ContextMenuItem>
            ) : (
              <ContextMenuItem key={s.label} onSelect={act(s)}>
                {s.icon}
                {s.label}
              </ContextMenuItem>
            ),
          ),
        ])}
      </ContextMenuContent>
    </ContextMenu>
  );
}

/** The row's "⋯": every shortcut the right-click menus offer, in one keyboard-reachable menu. */
export function RowActionsMenu({ label, groups }: { label: string; groups: Shortcut[][] }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-8" aria-label={`Actions for ${label}`}>
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {groups
          .filter((g) => g.length > 0)
          .map((group, i) => [
            i > 0 && <DropdownMenuSeparator key={`sep-${group[0]?.label}`} />,
            ...group.map((s) =>
              "href" in s ? (
                <DropdownMenuItem key={s.label} asChild>
                  <Link href={s.href}>
                    {s.icon}
                    {s.label}
                  </Link>
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem key={s.label} onSelect={act(s)}>
                  {s.icon}
                  {s.label}
                </DropdownMenuItem>
              ),
            ),
          ])}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The compound's registration number (its link), its name, and up to three other identifiers
 *  with "+N more" expanding the rest in place. */
export function CompoundIdentity({
  moleculeId,
  molecule: m,
}: {
  moleculeId: string;
  molecule: Molecule | undefined;
}) {
  const [expanded, setExpanded] = useState(false);
  const aliases = aliasesOf(m);
  const extra = aliases.length - 3;
  const shown = expanded ? aliases : aliases.slice(0, 3);
  return (
    <div className="flex min-w-0 flex-col gap-1 py-2 leading-tight">
      <Link
        href={`/compounds/${moleculeId}`}
        className="w-fit text-sm font-semibold text-foreground underline-offset-4 hover:underline"
      >
        {m?.registration_number ?? shortId(moleculeId)}
      </Link>
      {m?.name && m.name !== m.registration_number && (
        <span className="line-clamp-2 break-words text-xs text-muted-foreground" title={m.name}>
          {m.name}
        </span>
      )}
      {shown.map((a) => (
        <span
          key={a}
          className={cn("text-xs text-muted-foreground", expanded ? "break-words" : "truncate")}
          title={a}
        >
          {a}
        </span>
      ))}
      {extra > 0 && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
          className="w-fit text-xs italic text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          {expanded ? "Show less" : `+${extra} more`}
        </button>
      )}
    </div>
  );
}
