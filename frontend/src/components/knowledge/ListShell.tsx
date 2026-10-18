"use client";

import { ReactNode } from "react";
import { Loader2, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PAGE_SIZE } from "./usePagedList";

interface ListShellProps {
  loading: boolean;
  error: string | null;
  total: number;
  page: number;
  onPageChange: (page: number) => void;
  emptyText: string;
  children: ReactNode;
}

export function ListShell({
  loading,
  error,
  total,
  page,
  onPageChange,
  emptyText,
  children,
}: ListShellProps) {
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (loading) {
    return (
      <div className="flex justify-center py-12" role="status" aria-label="加载中">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <p role="alert" className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">
        {error}
      </p>
    );
  }

  if (total === 0) {
    return (
      <div className="flex flex-col items-center py-12 text-center text-sm text-slate-500">
        <Inbox className="mb-3 h-8 w-8 text-slate-400" aria-hidden="true" />
        {emptyText}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {children}
      {total > PAGE_SIZE && (
        <nav className="flex items-center justify-center gap-3 pt-4" aria-label="分页">
          <Button
            variant="outline"
            size="sm"
            className="rounded-full"
            disabled={page === 1}
            onClick={() => onPageChange(page - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-slate-600">
            {page} / {pageCount}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full"
            disabled={page >= pageCount}
            onClick={() => onPageChange(page + 1)}
          >
            下一页
          </Button>
        </nav>
      )}
    </div>
  );
}
