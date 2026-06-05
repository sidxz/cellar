"use client";

import { Button } from "@/shared/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface CurveNavigatorProps {
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}

export function CurveNavigator({ currentIndex, total, onPrev, onNext }: CurveNavigatorProps) {
  if (total <= 1) return null;

  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onPrev}>
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span className="font-mono tabular-nums">
        {currentIndex + 1} / {total}
      </span>
      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onNext}>
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
