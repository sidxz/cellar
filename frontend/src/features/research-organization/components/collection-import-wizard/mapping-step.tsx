"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";

type Role =
  | "registration_number"
  | "external_id"
  | "inchi_key"
  | "smiles"
  | "name"
  | "notes"
  | "ignore";

const ROLES: Role[] = [
  "registration_number",
  "external_id",
  "inchi_key",
  "smiles",
  "name",
  "notes",
  "ignore",
];

// Mirrors backend/src/cellar/application/research_organization/collection_import_mapping.py::_SYNONYMS
const SYNONYMS: Record<Exclude<Role, "ignore">, string[]> = {
  registration_number: [
    "regno",
    "reg",
    "regnumber",
    "registrationnumber",
    "registration",
    "compoundid",
    "cellarid",
    "ccnumber",
    "ccno",
    "compoundnumber",
  ],
  external_id: [
    "externalid",
    "vendorid",
    "vendorlot",
    "cas",
    "casnumber",
    "chemblid",
    "pubchemid",
    "suppliercode",
    "catalogno",
    "sku",
    "lotid",
    "lotnumber",
  ],
  inchi_key: ["inchikey", "inchi"],
  smiles: ["smiles", "canonicalsmiles", "structure", "molsmiles"],
  name: ["name", "compoundname", "moleculename", "commonname", "title", "label", "compound"],
  notes: ["notes", "note", "comment", "comments", "description", "remark"],
};

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function suggestRole(header: string): Role {
  const n = norm(header);
  for (const r of Object.keys(SYNONYMS) as Array<Exclude<Role, "ignore">>) {
    if (SYNONYMS[r].includes(n)) return r;
  }
  return "ignore";
}

interface TemplateLite {
  id: string;
  name: string;
  column_mapping: Record<string, string>;
  used_in_this_collection?: boolean;
  created_by?: string;
}

// Mirrors backend/src/cellar/application/research_organization/collection_import_templates.py::score_template_against_headers
function scoreTemplate(template: TemplateLite, headers: string[]): number {
  const normHeaders = new Set(headers.map(norm));
  const refs = Object.values(template.column_mapping).filter(Boolean);
  if (refs.length === 0) return 0;
  const matched = refs.filter((r) => normHeaders.has(norm(r))).length;
  return matched / refs.length;
}

type TemplateTier = "used_here" | "mine" | "workspace";

interface PickResult {
  template: TemplateLite;
  score: number;
  tier: TemplateTier;
}

function pickBestTemplate(
  templates: TemplateLite[],
  headers: string[],
  currentUserId?: string,
): PickResult | null {
  const tiers: { name: TemplateTier; filter: (t: TemplateLite) => boolean }[] = [
    { name: "used_here", filter: (t) => !!t.used_in_this_collection },
    {
      name: "mine",
      filter: (t) => !!currentUserId && t.created_by === currentUserId,
    },
    { name: "workspace", filter: () => true },
  ];
  for (const tier of tiers) {
    const candidates = templates.filter(tier.filter);
    let best: { template: TemplateLite; score: number } | null = null;
    for (const t of candidates) {
      const score = scoreTemplate(t, headers);
      if (score >= 0.7 && (!best || score > best.score)) {
        best = { template: t, score };
      }
    }
    if (best) return { ...best, tier: tier.name };
  }
  return null;
}

function tierFor(t: TemplateLite, currentUserId?: string): TemplateTier {
  if (t.used_in_this_collection) return "used_here";
  if (currentUserId && t.created_by === currentUserId) return "mine";
  return "workspace";
}

const TIER_MESSAGE: Record<TemplateTier, string> = {
  used_here: "used here before",
  mine: "your template",
  workspace: "best match",
};

type FilterChip = "all" | "used_here" | "mine";

interface AppliedTemplate {
  name: string;
  tier: TemplateTier;
}

export interface MappingStepProps {
  headers: string[];
  rows: Record<string, string>[];
  templates: TemplateLite[];
  currentUserId?: string;
  selectedTemplateId?: string | null;
  onSelectedTemplateChange?: (id: string | null) => void;
  onContinue: (output: {
    mapping: Record<string, string>;
    saveAsTemplate?: { name: string };
  }) => void;
  submitting?: boolean;
  /** Error from a failed template save, surfaced by the wizard. */
  templateError?: string | null;
  /**
   * Id of a template the wizard just saved from this session. When it changes,
   * the "save as template" toggle is cleared so the just-saved name doesn't
   * trip the duplicate-name guard against the template it created.
   */
  justSavedTemplateId?: string | null;
}

export function MappingStep({
  headers,
  rows: _rows,
  templates,
  currentUserId,
  selectedTemplateId: selectedTemplateIdProp,
  onSelectedTemplateChange,
  onContinue,
  submitting = false,
  templateError = null,
  justSavedTemplateId = null,
}: MappingStepProps) {
  const initial = useMemo<Record<string, Role>>(() => {
    const m: Record<string, Role> = {};
    for (const h of headers) m[h] = suggestRole(h);
    return m;
  }, [headers]);
  const [mapping, setMapping] = useState<Record<string, Role>>(initial);
  // Internal fallback when the composer doesn't lift state up (e.g. tests).
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);
  const selectedTemplateId =
    selectedTemplateIdProp !== undefined ? (selectedTemplateIdProp ?? null) : internalSelectedId;
  function setSelectedTemplateId(id: string | null) {
    setInternalSelectedId(id);
    onSelectedTemplateChange?.(id);
  }
  const [save, setSave] = useState(false);
  const [tplName, setTplName] = useState("");
  const [appliedTemplate, setAppliedTemplate] = useState<AppliedTemplate | null>(null);
  const [filter, setFilter] = useState<FilterChip>("all");
  const autoAppliedRef = useRef(false);
  const clearedSaveForRef = useRef<string | null>(null);

  // Once the wizard reports a successful save, the "save as template" intent is
  // fulfilled — clear the toggle so the just-saved name doesn't immediately
  // trip the duplicate-name guard against the template it just created.
  useEffect(() => {
    if (justSavedTemplateId && justSavedTemplateId !== clearedSaveForRef.current) {
      clearedSaveForRef.current = justSavedTemplateId;
      setSave(false);
      setTplName("");
    }
  }, [justSavedTemplateId]);

  const filteredTemplates = useMemo(() => {
    if (filter === "used_here") {
      return templates.filter((t) => t.used_in_this_collection);
    }
    if (filter === "mine") {
      return templates.filter((t) => !!currentUserId && t.created_by === currentUserId);
    }
    return templates;
  }, [filter, templates, currentUserId]);

  const usedHereCount = useMemo(
    () => templates.filter((t) => t.used_in_this_collection).length,
    [templates],
  );
  const mineCount = useMemo(
    () => templates.filter((t) => !!currentUserId && t.created_by === currentUserId).length,
    [templates, currentUserId],
  );

  function applyTemplate(id: string) {
    if (!id) {
      // "Choose template…" — clear selection but don't reset the auto-apply guard.
      setSelectedTemplateId(null);
      return;
    }
    const tpl = templates.find((x) => x.id === id);
    if (!tpl) return;
    setSelectedTemplateId(id);
    const next: Record<string, Role> = {};
    for (const h of headers) next[h] = "ignore";
    for (const [role, header] of Object.entries(tpl.column_mapping)) {
      if (headers.includes(header)) next[header] = role as Role;
    }
    setMapping(next);
    // Manual pick — show the indicator (with tier) and prevent the auto-effect
    // from overwriting later.
    setAppliedTemplate({ name: tpl.name, tier: tierFor(tpl, currentUserId) });
    autoAppliedRef.current = true;
  }

  // biome-ignore lint/correctness/useExhaustiveDependencies: the state setters (setMapping/setSelectedTemplateId/setAppliedTemplate) are stable; auto-apply keys only on templates/headers/currentUserId.
  useEffect(() => {
    if (autoAppliedRef.current) return;
    if (templates.length === 0) return;
    const result = pickBestTemplate(templates, headers, currentUserId);
    if (!result) return;
    const next: Record<string, Role> = {};
    for (const h of headers) next[h] = "ignore";
    for (const [role, header] of Object.entries(result.template.column_mapping)) {
      if (headers.includes(header)) next[header] = role as Role;
    }
    setMapping(next);
    setSelectedTemplateId(result.template.id);
    setAppliedTemplate({ name: result.template.name, tier: result.tier });
    autoAppliedRef.current = true;
  }, [templates, headers, currentUserId]);

  function buildOutput() {
    const out: Record<string, string> = {};
    for (const h of headers) {
      const r = mapping[h];
      if (r !== "ignore") out[r] = h;
    }
    return out;
  }

  // Client-side guard so a name collision is caught instantly (instead of a
  // failed round-trip), matching the BE's unique (workspace, name) constraint.
  const trimmedTplName = tplName.trim();
  const isDuplicateName =
    save && trimmedTplName.length > 0 && templates.some((t) => t.name.trim() === trimmedTplName);
  // When the chemist opts to save, require a valid name before continuing so
  // the intent isn't silently dropped.
  const saveBlocksContinue = save && (trimmedTplName.length === 0 || isDuplicateName);

  return (
    <div className="space-y-6">
      {templates.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant={filter === "all" ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter("all")}
          >
            All ({templates.length})
          </Button>
          <Button
            type="button"
            variant={filter === "used_here" ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter("used_here")}
          >
            Used here ({usedHereCount})
          </Button>
          <Button
            type="button"
            variant={filter === "mine" ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter("mine")}
          >
            Mine ({mineCount})
          </Button>
        </div>
      )}
      {templates.length > 0 && (
        <div className="space-y-2">
          <Label htmlFor="template-picker">Apply a saved template</Label>
          <select
            id="template-picker"
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={selectedTemplateId ?? ""}
            onChange={(e) => applyTemplate(e.target.value)}
          >
            <option value="">Choose template…</option>
            {filteredTemplates.map((t) => {
              const tags: string[] = [];
              if (t.used_in_this_collection) tags.push("used here");
              if (currentUserId && t.created_by === currentUserId) tags.push("mine");
              const suffix = tags.length > 0 ? ` (${tags.join(", ")})` : "";
              return (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {suffix}
                </option>
              );
            })}
          </select>
        </div>
      )}
      {appliedTemplate && (
        <div className="rounded border border-emerald-300 bg-emerald-50 p-3 text-sm">
          <p className="text-emerald-900">
            ✓ Applied saved template &ldquo;{appliedTemplate.name}&rdquo; —{" "}
            {TIER_MESSAGE[appliedTemplate.tier]}. You can override below or pick a different
            template above.
          </p>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>CSV column</TableHead>
            <TableHead>Role</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {headers.map((h) => (
            <TableRow key={h}>
              <TableCell className="font-mono text-sm">{h}</TableCell>
              <TableCell>
                <Label htmlFor={`role-${h}`} className="sr-only">
                  Role for {h}
                </Label>
                <select
                  id={`role-${h}`}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={mapping[h]}
                  onChange={(e) => setMapping((m) => ({ ...m, [h]: e.target.value as Role }))}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="flex items-center gap-2">
        <Checkbox id="save" checked={save} onCheckedChange={(v) => setSave(!!v)} />
        <Label htmlFor="save">Save this mapping as a workspace template</Label>
      </div>
      {templates.length === 0 && !save && (
        <p className="text-xs text-muted-foreground">
          No saved templates yet. Tick the box above to save this mapping now and reuse it next
          time.
        </p>
      )}
      {save && (
        <div className="space-y-1">
          <Input
            placeholder="Template name"
            value={tplName}
            onChange={(e) => setTplName(e.target.value)}
            aria-invalid={isDuplicateName || undefined}
          />
          {isDuplicateName && !submitting && (
            <p className="text-xs text-destructive">
              A template named &ldquo;{trimmedTplName}&rdquo; already exists. Pick a different name.
            </p>
          )}
          {(!isDuplicateName || submitting) && (
            <p className="text-xs text-muted-foreground">
              Saved as soon as you continue — independent of the import.
            </p>
          )}
        </div>
      )}
      {templateError && <p className="text-sm text-destructive">{templateError}</p>}
      <Button
        disabled={submitting || saveBlocksContinue}
        onClick={() =>
          onContinue({
            mapping: buildOutput(),
            saveAsTemplate: save && trimmedTplName ? { name: trimmedTplName } : undefined,
          })
        }
      >
        {submitting ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Resolving…
          </>
        ) : (
          "Continue"
        )}
      </Button>
    </div>
  );
}
