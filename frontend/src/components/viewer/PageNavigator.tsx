"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, FileText } from "lucide-react";

interface PageNavigatorProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function PageNavigator({
  currentPage,
  totalPages,
  onPageChange,
}: PageNavigatorProps) {
  const [inputValue, setInputValue] = useState(String(currentPage));

  useEffect(() => {
    setInputValue(String(currentPage));
  }, [currentPage]);

  const commitPage = () => {
    const page = Number(inputValue);
    if (!Number.isFinite(page)) {
      setInputValue(String(currentPage));
      return;
    }

    const nextPage = Math.min(Math.max(Math.trunc(page), 1), totalPages);
    setInputValue(String(nextPage));

    if (nextPage !== currentPage) {
      onPageChange(nextPage);
    }
  };

  return (
    <div className="mt-2 flex shrink-0 flex-wrap gap-2 rounded-lg border border-border bg-white/80 px-2 py-2 shadow-none items-center justify-between">
      <Button
        variant="outline"
        size="sm"
        className="rounded-full border-border bg-white/80"
        disabled={currentPage <= 1}
        onClick={() => onPageChange(currentPage - 1)}
      >
        <ChevronLeft className="mr-1 h-4 w-4" />
        上一页
      </Button>

      <div className="flex flex-wrap items-center justify-center gap-1 rounded-md bg-muted px-2 py-1 text-sm text-slate-600">
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={totalPages}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onBlur={commitPage}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                commitPage();
              }
            }}
            className="w-16 rounded-full border border-slate-200 bg-white px-3 py-1 text-center text-sm font-medium text-slate-900 outline-none transition focus:border-primary/40"
          />
          <span>/ {totalPages}</span>
        </div>
      </div>

      <Button
        variant="outline"
        size="sm"
        className="rounded-full border-border bg-white/80"
        disabled={currentPage >= totalPages}
        onClick={() => onPageChange(currentPage + 1)}
      >
        下一页
        <ChevronRight className="ml-1 h-4 w-4" />
      </Button>
    </div>
  );
}
