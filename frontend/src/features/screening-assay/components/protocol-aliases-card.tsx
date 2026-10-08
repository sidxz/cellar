"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { X } from "lucide-react";
import { useState } from "react";
import { useAddProtocolNickname, useRemoveProtocolNickname } from "../hooks/use-protocols";
import type { Protocol } from "../types";

interface ProtocolAliasesCardProps {
  protocol: Protocol;
  canEdit: boolean;
}

/** Names people use for a protocol (MABA, HLM CLint) plus the names it had before.
 *  Searchable everywhere; never rendered as the protocol's name. */
export function ProtocolAliasesCard({ protocol, canEdit }: ProtocolAliasesCardProps) {
  const [draft, setDraft] = useState("");
  const add = useAddProtocolNickname(protocol.id);
  const remove = useRemoveProtocolNickname(protocol.id);
  const aliases = protocol.aliases ?? [];
  const nicknames = aliases.filter((a) => a.kind === "nickname");
  const formers = aliases.filter((a) => a.kind === "former");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Also known as</CardTitle>
        <CardDescription>
          Names people use for this protocol. They are searchable but never become its name.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {nicknames.length === 0 && (
            <p className="text-sm text-muted-foreground">No nicknames yet.</p>
          )}
          {nicknames.map((a) => (
            <Badge key={a.label} variant="secondary" className="gap-1 pr-1">
              {a.label}
              {canEdit && (
                <button
                  type="button"
                  aria-label={`Remove ${a.label}`}
                  onClick={() => remove.mutate(a.label)}
                  className="rounded p-0.5 hover:bg-muted"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
        {canEdit && (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const label = draft.trim();
              if (label) add.mutate(label, { onSuccess: () => setDraft("") });
            }}
          >
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="e.g. MABA, HLM CLint"
              aria-label="New nickname"
              className="max-w-xs"
            />
            <Button
              type="submit"
              variant="outline"
              size="sm"
              disabled={!draft.trim() || add.isPending}
            >
              Add
            </Button>
          </form>
        )}
        {formers.length > 0 && (
          <div className="text-sm text-muted-foreground">
            <p className="font-medium">Former names</p>
            <ul className="mt-1 space-y-0.5">
              {formers.map((a) => (
                <li key={`${a.label}-${a.recorded_at}`}>
                  {a.label}{" "}
                  <span className="text-xs">
                    (until {new Date(a.recorded_at).toLocaleDateString()}
                    {a.reason ? `, ${a.reason}` : ""})
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
