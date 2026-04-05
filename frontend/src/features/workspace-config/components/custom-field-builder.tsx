"use client";

import { GripVertical, Plus, Trash2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useVocabularies } from "../hooks/use-vocabularies";
import type { CustomFieldDefinition } from "../types";

const DATA_TYPE_LABELS: Record<CustomFieldDefinition["data_type"], string> = {
  text: "Text",
  number: "Number",
  date: "Date",
  select: "Select (Vocabulary)",
};

interface CustomFieldBuilderProps {
  fields: CustomFieldDefinition[];
  onChange: (fields: CustomFieldDefinition[]) => void;
}

export function CustomFieldBuilder({
  fields,
  onChange,
}: CustomFieldBuilderProps) {
  const { data: vocabularies } = useVocabularies();

  const addField = () => {
    onChange([
      ...fields,
      { name: "", label: "", data_type: "text", required: false },
    ]);
  };

  const removeField = (index: number) => {
    onChange(fields.filter((_, i) => i !== index));
  };

  const updateField = (
    index: number,
    patch: Partial<CustomFieldDefinition>
  ) => {
    onChange(
      fields.map((f, i) => (i === index ? { ...f, ...patch } : f))
    );
  };

  return (
    <div className="space-y-3">
      {fields.map((field, index) => (
        <Card key={index}>
          <CardContent className="pt-4">
            <div className="flex items-start gap-2">
              <GripVertical className="mt-2 h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="grid flex-1 gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-1">
                    <Label className="text-xs">Field Name (key)</Label>
                    <Input
                      placeholder="e.g., project_code"
                      value={field.name}
                      onChange={(e) =>
                        updateField(index, { name: e.target.value })
                      }
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Display Label</Label>
                    <Input
                      placeholder="e.g., Project Code"
                      value={field.label}
                      onChange={(e) =>
                        updateField(index, { label: e.target.value })
                      }
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-1">
                    <Label className="text-xs">Data Type</Label>
                    <Select
                      value={field.data_type}
                      onValueChange={(v) =>
                        updateField(index, {
                          data_type: v as CustomFieldDefinition["data_type"],
                          vocabulary_name:
                            v === "select" ? field.vocabulary_name : null,
                        })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(DATA_TYPE_LABELS).map(
                          ([value, label]) => (
                            <SelectItem key={value} value={value}>
                              {label}
                            </SelectItem>
                          )
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  {field.data_type === "select" && (
                    <div className="grid gap-1">
                      <Label className="text-xs">Vocabulary</Label>
                      <Select
                        value={field.vocabulary_name ?? ""}
                        onValueChange={(v) =>
                          updateField(index, { vocabulary_name: v || null })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select vocabulary..." />
                        </SelectTrigger>
                        <SelectContent>
                          {vocabularies?.map((v) => (
                            <SelectItem key={v.id} value={v.name}>
                              {v.name} ({v.terms.length} terms)
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Checkbox
                    id={`required-${index}`}
                    checked={field.required}
                    onCheckedChange={(checked) =>
                      updateField(index, { required: checked === true })
                    }
                  />
                  <Label htmlFor={`required-${index}`} className="text-xs">
                    Required
                  </Label>
                </div>
              </div>

              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="mt-1 shrink-0"
                onClick={() => removeField(index)}
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}

      <Button type="button" variant="outline" size="sm" onClick={addField}>
        <Plus className="mr-2 h-4 w-4" />
        Add Custom Field
      </Button>
    </div>
  );
}
