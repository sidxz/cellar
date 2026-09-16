"use client";

import { Button } from "@/shared/components/ui/button";
import { Textarea } from "@/shared/components/ui/textarea";
import type { CommentTarget } from "@/shared/lib/api/model";
import { formatDateTime } from "@/shared/lib/format-date";
import Link from "next/link";
import { useState } from "react";
import { type CommentScope, useAddComment, useComments } from "../hooks/use-comments";

export interface CommentFeedProps {
  /** What to LIST: one target, or everything written in a loan's context. */
  scope: CommentScope;
  /** Editors may append; viewers only read. */
  canWrite: boolean;
  /** Where a new comment is POSTED. Defaults to `scope` when it is a target
   *  scope; required to enable the composer on a loanId scope (the loan card
   *  lists the whole loan context but posts to the loan itself). */
  composerTarget?: { targetType: CommentTarget; targetId: string };
  /** Extra context sent with a new comment (a group/plate comment made from a loan card). */
  loanContextId?: string;
  emptyText?: string;
}

export function CommentFeed({
  scope,
  canWrite,
  composerTarget,
  loanContextId,
  emptyText = "No comments yet.",
}: CommentFeedProps) {
  const { data: comments, isLoading } = useComments(scope);
  const add = useAddComment();
  const [draft, setDraft] = useState("");
  const postTarget = composerTarget ?? ("targetType" in scope ? scope : undefined);
  const ownLoanId = "loanId" in scope ? scope.loanId : null;

  const submit = () => {
    if (!postTarget || !draft.trim()) return;
    add.mutate(
      {
        target_type: postTarget.targetType,
        target_id: postTarget.targetId,
        body: draft.trim(),
        loan_id: loanContextId ?? null,
      },
      { onSuccess: () => setDraft("") },
    );
  };

  return (
    <div className="flex flex-col gap-3" data-testid="comment-feed">
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !comments?.length ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {comments.map((c) => (
            <li key={c.id} className="px-3 py-2 text-sm">
              <div className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{c.author_name}</span>
                <span className="flex items-center gap-2">
                  {c.loan_id && c.loan_id !== ownLoanId ? (
                    <Link
                      href={`/inventory/loans/${c.loan_id}`}
                      className="text-xs text-primary hover:underline"
                    >
                      view loan
                    </Link>
                  ) : null}
                  <time dateTime={c.created_at}>{formatDateTime(c.created_at)}</time>
                </span>
              </div>
              <p className="mt-1 whitespace-pre-wrap">{c.body}</p>
            </li>
          ))}
        </ul>
      )}
      {canWrite && postTarget ? (
        <div className="flex flex-col gap-2">
          <Textarea
            aria-label="New comment"
            rows={2}
            maxLength={5000}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a comment…"
          />
          <div>
            <Button size="sm" onClick={submit} disabled={!draft.trim() || add.isPending}>
              {add.isPending ? "Adding…" : "Add comment"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
