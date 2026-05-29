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
  name: [
    "name",
    "compoundname",
    "moleculename",
    "commonname",
    "title",
    "label",
    "compound",
  ],
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
}

// Mirrors backend/src/cellar/application/research_organization/collection_import_templates.py::score_template_against_headers
function scoreTemplate(template: TemplateLite, headers: string[]): number {
  const normHeaders = new Set(headers.map(norm));
  const refs = Object.values(template.column_mapping).filter(Boolean);
  if (refs.length === 0) return 0;
  const matched = refs.filter((r) => normHeaders.has(norm(r))).length;
  return matched / refs.length;
}

function pickBestTemplate(
  templates: TemplateLite[],
  headers: string[],
): { template: TemplateLite; score: number } | null {
  let best: { template: TemplateLite; score: number } | null = null;
  for (const t of templates) {
    const score = scoreTemplate(t, headers);
    if (score >= 0.7 && (!best || score > best.score)) {
      best = { template: t, score };
    }
  }
  return best;
}

export interface MappingStepProps {
  headers: string[];
  rows: Record<string, string>[];
  templates: TemplateLite[];
  onContinue: (output: {
    mapping: Record<string, string>;
    saveAsTemplate?: { name: string };
  }) => void;
  submitting?: boolean;
}

export function MappingStep({
  headers,
  rows: _rows,
  templates,
  onContinue,
  submitting = false,
}: MappingStepProps) {
  const initial = useMemo<Record<string, Role>>(() => {
    const m: Record<string, Role> = {};
    for (const h of headers) m[h] = suggestRole(h);
    return m;
  }, [headers]);
  const [mapping, setMapping] = useState<Record<string, Role>>(initial);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [save, setSave] = useState(false);
  const [tplName, setTplName] = useState("");
  const [appliedTemplateName, setAppliedTemplateName] = useState<string | null>(
    null,
  );
  const autoAppliedRef = useRef(false);

  function applyTemplate(id: string) {
    setSelectedTemplateId(id);
    const tpl = templates.find((x) => x.id === id);
    if (!tpl) return;
    const next: Record<string, Role> = {};
    for (const h of headers) next[h] = "ignore";
    for (const [role, header] of Object.entries(tpl.column_mapping)) {
      if (headers.includes(header)) next[header] = role as Role;
    }
    setMapping(next);
    // Manual pick — show the indicator too (and don't let the auto-effect overwrite later).
    setAppliedTemplateName(tpl.name);
    autoAppliedRef.current = true;
  }

  useEffect(() => {
    if (autoAppliedRef.current) return;
    if (templates.length === 0) return;
    const best = pickBestTemplate(templates, headers);
    if (!best) return;
    const next: Record<string, Role> = {};
    for (const h of headers) next[h] = "ignore";
    for (const [role, header] of Object.entries(best.template.column_mapping)) {
      if (headers.includes(header)) next[header] = role as Role;
    }
    setMapping(next);
    setSelectedTemplateId(best.template.id);
    setAppliedTemplateName(best.template.name);
    autoAppliedRef.current = true;
  }, [templates, headers]);

  function buildOutput() {
    const out: Record<string, string> = {};
    for (const h of headers) {
      const r = mapping[h];
      if (r !== "ignore") out[r] = h;
    }
    return out;
  }

  return (
    <div className="space-y-6">
      {templates.length > 0 && (
        <div className="space-y-2">
          <Label htmlFor="template-picker">Apply a saved template</Label>
          <select
            id="template-picker"
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={selectedTemplateId}
            onChange={(e) => applyTemplate(e.target.value)}
          >
            <option value="">Choose template…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {appliedTemplateName && (
        <div className="rounded border border-emerald-300 bg-emerald-50 p-3 text-sm">
          <p className="text-emerald-900">
            ✓ Applied saved template &ldquo;{appliedTemplateName}&rdquo;. You
            can override below or pick a different template above.
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
                  onChange={(e) =>
                    setMapping((m) => ({ ...m, [h]: e.target.value as Role }))
                  }
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
        <Checkbox
          id="save"
          checked={save}
          onCheckedChange={(v) => setSave(!!v)}
        />
        <Label htmlFor="save">Save this mapping as a workspace template</Label>
      </div>
      {templates.length === 0 && !save && (
        <p className="text-xs text-muted-foreground">
          No saved templates yet. Save this mapping at the end to reuse it next
          time.
        </p>
      )}
      {save && (
        <Input
          placeholder="Template name"
          value={tplName}
          onChange={(e) => setTplName(e.target.value)}
        />
      )}
      <Button
        disabled={submitting}
        onClick={() =>
          onContinue({
            mapping: buildOutput(),
            saveAsTemplate: save && tplName ? { name: tplName } : undefined,
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
