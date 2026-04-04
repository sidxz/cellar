"use client";

import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  useCreateVocabulary,
  useUpdateVocabulary,
} from "../hooks/use-vocabularies";
import type { Vocabulary } from "../types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  vocabulary: Vocabulary | null;
}

export function VocabularyDialog({ open, onOpenChange, vocabulary }: Props) {
  const [name, setName] = useState("");
  const [terms, setTerms] = useState<string[]>([]);
  const [newTerm, setNewTerm] = useState("");
  const [isLocked, setIsLocked] = useState(false);

  const create = useCreateVocabulary();
  const update = useUpdateVocabulary(vocabulary?.id ?? "");
  const isEdit = vocabulary !== null;

  useEffect(() => {
    if (vocabulary) {
      setName(vocabulary.name);
      setTerms([...vocabulary.terms]);
      setIsLocked(vocabulary.is_locked);
    } else {
      setName("");
      setTerms([]);
      setIsLocked(false);
    }
    setNewTerm("");
  }, [vocabulary, open]);

  const addTerm = () => {
    const trimmed = newTerm.trim();
    if (trimmed && !terms.includes(trimmed)) {
      setTerms([...terms, trimmed]);
      setNewTerm("");
    }
  };

  const removeTerm = (term: string) => {
    setTerms(terms.filter((t) => t !== term));
  };

  const handleSubmit = async () => {
    if (isEdit) {
      await update.mutateAsync({ name, terms, is_locked: isLocked });
    } else {
      await create.mutateAsync({ name, terms });
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Vocabulary" : "New Vocabulary"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="vocab-name">Name</Label>
            <Input
              id="vocab-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Species, Route of Administration"
            />
          </div>
          <div className="grid gap-2">
            <Label>Terms</Label>
            <div className="flex gap-2">
              <Input
                value={newTerm}
                onChange={(e) => setNewTerm(e.target.value)}
                placeholder="Add a term..."
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addTerm();
                  }
                }}
              />
              <Button type="button" variant="outline" size="icon" onClick={addTerm}>
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            {terms.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {terms.map((term) => (
                  <Badge key={term} variant="secondary" className="gap-1">
                    {term}
                    <button
                      type="button"
                      onClick={() => removeTerm(term)}
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>
          {isEdit && (
            <div className="flex items-center gap-2">
              <input
                id="locked"
                type="checkbox"
                checked={isLocked}
                onChange={(e) => setIsLocked(e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              <Label htmlFor="locked" className="cursor-pointer">
                Lock vocabulary (admin-only edits)
              </Label>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!name.trim() || create.isPending || update.isPending}
          >
            {create.isPending || update.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
