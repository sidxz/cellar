"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import type { Protocol, Run } from "../types";
import { RunNotesLine } from "./run-notes-line";
import {
  CollectionsRelation,
  ConditionsRelation,
  TagsRelation,
  TargetsRelation,
} from "./run-relations";

export function RunDetailsPanel({
  run,
  protocol,
  canEdit,
}: {
  run: Run;
  protocol: Protocol | undefined;
  canEdit: boolean;
}) {
  const canEditMeta = canEdit && !run.is_locked;

  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Notes and provenance</CardTitle>
        </CardHeader>
        <CardContent>
          <RunNotesLine run={run} canEdit={canEditMeta} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Run context</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-start gap-5">
          <TargetsRelation run={run} canEdit={canEditMeta} />
          <CollectionsRelation run={run} protocol={protocol} canEdit={canEditMeta} />
          <ConditionsRelation run={run} protocol={protocol} canEdit={canEditMeta} />
          <TagsRelation runId={run.id} canEdit={canEdit} />
        </CardContent>
      </Card>
    </div>
  );
}
