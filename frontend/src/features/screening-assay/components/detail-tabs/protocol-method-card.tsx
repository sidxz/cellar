"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { useAuthzHasRole } from "@duar-auth/nextjs";
import { Paperclip, Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useCorrectProtocol, useUpdateProtocol } from "../../hooks/use-protocols";
import { METHOD_PLACEHOLDER } from "../../lib/protocol-method";
import type { Protocol } from "../../types";

/** Past this many lines the method shows clamped, with "Show all". */
const CLAMP_LINES = 12;

/** The protocol's method, first on the Overview: how the assay is run, written by the scientist.
 *  A draft's method is edited freely; a published one is corrected with a reason (a changed
 *  procedure is a new version); locked and retired ones are read-only. */
export function ProtocolMethodCard({
  protocol,
  onOpenFiles,
}: {
  protocol: Protocol;
  onOpenFiles: () => void;
}) {
  const isEditor = useAuthzHasRole("editor");
  const editable =
    isEditor &&
    !protocol.is_locked &&
    (protocol.status === "draft" || protocol.status === "active");
  const needsReason = protocol.status === "active";
  // What was just saved, until the refetched protocol replaces the text it was saved over: a quick
  // reopen must start from the new method, or a second save would quietly put the old one back.
  const [justSaved, setJustSaved] = useState<{ over: string | null; text: string | null } | null>(
    null,
  );
  const fromServer = protocol.description ?? null;
  // Once the server's text moves off what was saved over, it is the truth from then on (even if
  // a later change brings the old text back).
  if (justSaved && justSaved.over !== fromServer) setJustSaved(null);
  const saved = (justSaved && justSaved.over === fromServer ? justSaved.text : fromServer) ?? "";

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(saved);
  const [reason, setReason] = useState("");
  const [expanded, setExpanded] = useState(false);

  // Opening the editor puts the caret at the end: a method is usually added to, not rewritten.
  const textRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const ta = textRef.current;
    if (!editing || !ta) return;
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  }, [editing]);

  const update = useUpdateProtocol(protocol.id);
  const correct = useCorrectProtocol(protocol.id);
  const pending = update.isPending || correct.isPending;

  const open = () => {
    setDraft(saved);
    setReason("");
    setEditing(true);
  };
  const close = () => setEditing(false);

  const dirty = draft.trim() !== saved.trim();
  const canSave = dirty && (!needsReason || reason.trim() !== "") && !pending;
  const save = () => {
    if (!canSave) return;
    const description = draft.trim() || null;
    const onSuccess = () => {
      setJustSaved({ over: fromServer, text: description });
      close();
    };
    if (needsReason) {
      correct.mutate({ reason: reason.trim(), description }, { onSuccess });
    } else {
      update.mutate({ description }, { onSuccess });
    }
  };

  const long = saved.split("\n").length > CLAMP_LINES || saved.length > 1200;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Method</CardTitle>
        <Button variant="ghost" size="sm" className="h-auto px-2 py-1" onClick={onOpenFiles}>
          <Paperclip className="mr-1.5 h-3.5 w-3.5" />
          SOP and files
        </Button>
      </CardHeader>
      <CardContent>
        {editing ? (
          <div className="grid gap-3">
            <Textarea
              ref={textRef}
              aria-label="Method"
              className="min-h-60"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  close();
                } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  save();
                }
              }}
              placeholder={METHOD_PLACEHOLDER}
              disabled={pending}
            />
            {needsReason && (
              <div className="grid gap-1.5">
                <Label htmlFor="method-reason">Reason for the change</Label>
                <Input
                  id="method-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. Fixed a typo; added the read wavelength"
                  disabled={pending}
                />
                <p className="text-xs text-muted-foreground">
                  This protocol is published, so the change is recorded with your reason. If the
                  procedure itself changes (steps, reagents, detection), make a new version; values
                  that differ from run to run are assay conditions.
                </p>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={close} disabled={pending}>
                Cancel
              </Button>
              <Button size="sm" onClick={save} disabled={!canSave}>
                {pending ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        ) : saved ? (
          <div className="grid gap-1">
            <MethodText
              text={saved}
              clamped={long && !expanded}
              onEdit={editable ? open : undefined}
            />
            {long && (
              <Button
                variant="link"
                size="sm"
                className="h-auto justify-self-start p-0"
                onClick={() => setExpanded((e) => !e)}
              >
                {expanded ? "Show less" : "Show all"}
              </Button>
            )}
          </div>
        ) : editable ? (
          <button
            type="button"
            onClick={open}
            className="group -ml-1 inline-flex items-start gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted/50 focus:bg-muted/60 focus:outline-none"
          >
            <span className="text-sm italic text-muted-foreground/70">
              Add the method: how the assay is run, so a colleague can repeat it…
            </span>
            <Pencil className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground" />
          </button>
        ) : (
          <p className="text-sm text-muted-foreground">No method recorded.</p>
        )}
      </CardContent>
    </Card>
  );
}

/** The text keeps its line breaks; when editable the text itself is the edit target. */
function MethodText({
  text,
  clamped,
  onEdit,
}: {
  text: string;
  clamped: boolean;
  onEdit?: () => void;
}) {
  const body = (
    <span
      className={`block whitespace-pre-wrap text-sm leading-relaxed ${clamped ? "line-clamp-12" : ""}`}
    >
      {text}
    </span>
  );
  if (!onEdit) return body;
  return (
    <button
      type="button"
      onClick={onEdit}
      aria-label="Edit method"
      className="group -ml-1 flex w-full items-start gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted/50 focus:bg-muted/60 focus:outline-none"
    >
      <span className="min-w-0 flex-1">{body}</span>
      <Pencil className="mt-1 h-3 w-3 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground" />
    </button>
  );
}
