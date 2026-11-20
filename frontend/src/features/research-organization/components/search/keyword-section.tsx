"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import {
  MAX_KEYWORD_VALUES,
  formatKeywordValues,
  parseKeywordValues,
} from "../../lib/keyword-values";
import type { KeywordCriterion, KeywordListCriterion, TextOperator } from "../../types";

const KEYWORD_FIELDS = [
  { value: "any", label: "Any field" },
  { value: "name", label: "Name" },
  { value: "registration_number", label: "Compound ID" },
  { value: "external_id", label: "External ID" },
  { value: "molecular_formula", label: "Formula" },
  { value: "inchi_key", label: "InChI Key" },
  { value: "smiles", label: "SMILES" },
] as const;

const TEXT_OPERATORS: { value: TextOperator; label: string }[] = [
  { value: "contains", label: "Contains" },
  { value: "equals", label: "Equals" },
  { value: "starts_with", label: "Starts with" },
];

export function defaultKeywordCriterion(): KeywordListCriterion {
  return { type: "keyword_list", ref_type: "any", operator: "contains", values: [] };
}

function KeywordTerm({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: KeywordCriterion;
  onChange: (c: KeywordCriterion) => void;
  onRemove: () => void;
}) {
  const field = criterion.type === "text" ? criterion.field : criterion.ref_type;
  const operator = criterion.operator ?? "equals";
  const values = criterion.type === "text" ? [criterion.value] : criterion.values;
  const canonicalValues = JSON.stringify(values);
  const [rawText, setRawText] = useState(() => formatKeywordValues(values));
  const lastCommitted = useRef(canonicalValues);
  // Until the chemist picks a match, one term reads as "contains" and a pasted list as
  // "equals": a list of IDs must not also match every longer ID that contains one of them.
  const operatorPicked = useRef(values.length > 0);
  const helpId = useId();
  const valueCount = values.filter(Boolean).length;
  const tooMany = valueCount > MAX_KEYWORD_VALUES;

  // Saved-search loads replace the input; our own commits keep delimiters and the caret intact.
  useEffect(() => {
    if (canonicalValues === lastCommitted.current) return;
    lastCommitted.current = canonicalValues;
    operatorPicked.current = true;
    setRawText(formatKeywordValues(JSON.parse(canonicalValues)));
  }, [canonicalValues]);

  function update(patch: Partial<KeywordListCriterion>) {
    onChange({
      type: "keyword_list",
      ref_type: field as KeywordListCriterion["ref_type"],
      operator,
      values,
      ...(criterion.negate ? { negate: true } : {}),
      ...patch,
    });
  }

  function handleTextChange(text: string) {
    setRawText(text);
    const parsed = parseKeywordValues(text);
    lastCommitted.current = JSON.stringify(parsed);
    update({
      values: parsed,
      ...(operatorPicked.current || field === "smiles" || field === "uuid"
        ? {}
        : { operator: parsed.length > 1 ? "equals" : "contains" }),
    });
  }

  return (
    <div className="space-y-2 rounded-lg border border-border/70 p-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="w-full min-w-0 sm:w-40 sm:shrink-0">
          <Select
            value={field}
            onValueChange={(value) =>
              update({
                ref_type: value as KeywordListCriterion["ref_type"],
                ...(value === "smiles" || value === "uuid" ? { operator: "equals" } : {}),
              })
            }
          >
            <SelectTrigger size="sm" className="w-full min-w-0 text-sm" aria-label="Keyword field">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KEYWORD_FIELDS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
              {field === "uuid" && <SelectItem value="uuid">Internal ID</SelectItem>}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0 flex-1 sm:w-36 sm:flex-none">
          <Select
            value={operator}
            disabled={field === "smiles" || field === "uuid"}
            onValueChange={(value) => {
              operatorPicked.current = true;
              update({ operator: value as TextOperator });
            }}
          >
            <SelectTrigger size="sm" className="w-full min-w-0 text-sm" aria-label="Keyword match">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TEXT_OPERATORS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {criterion.negate && <span className="text-xs text-muted-foreground">Exclude matches</span>}
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove keyword condition"
          className="ml-auto flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <textarea
        className="flex min-h-24 w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Keyword values"
        aria-describedby={helpId}
        placeholder="Enter a keyword or paste values separated by commas or new lines…"
        value={rawText}
        onChange={(event) => handleTextChange(event.target.value)}
      />
      <div
        id={helpId}
        className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground"
      >
        <span>Matches any value. Use quotes around a value containing a comma.</span>
        <span className={tooMany ? "font-medium text-destructive" : undefined}>
          {valueCount.toLocaleString()} value{valueCount === 1 ? "" : "s"}
          {tooMany && ` · up to ${MAX_KEYWORD_VALUES.toLocaleString()} per term`}
        </span>
      </div>
    </div>
  );
}

interface KeywordSectionProps {
  criteria: KeywordCriterion[];
  onChange: (criteria: KeywordCriterion[]) => void;
}

export function KeywordSection({ criteria, onChange }: KeywordSectionProps) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Keywords
        </span>
        <button
          type="button"
          onClick={() => onChange([...criteria, defaultKeywordCriterion()])}
          className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary transition-colors hover:bg-primary/20"
        >
          <Plus className="h-3 w-3" /> Add term
        </button>
      </div>
      <p className="text-xs text-muted-foreground">
        Search compound IDs, names, formulas, InChIKeys, and external IDs. Add terms to narrow your
        results.
      </p>
      {criteria.map((criterion, index) => (
        <KeywordTerm
          key={`keyword-${index}`}
          criterion={criterion}
          onChange={(updated) => onChange(criteria.map((c, i) => (i === index ? updated : c)))}
          onRemove={() => onChange(criteria.filter((_, i) => i !== index))}
        />
      ))}
    </div>
  );
}
