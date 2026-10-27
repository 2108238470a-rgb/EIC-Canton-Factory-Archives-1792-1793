"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { knowledgeApi } from "@/lib/api";
import { ListShell } from "./ListShell";
import { usePagedList } from "./usePagedList";

export function EvidenceList() {
  const router = useRouter();
  const list = usePagedList(knowledgeApi.listEvidence);
  const [locating, setLocating] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const openInViewer = async (spanId: number) => {
    setLocating(spanId);
    setError(null);
    try {
      const locator = await knowledgeApi.getEvidenceLocator(spanId);
      router.push(locator.viewer_path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "定位失败");
      setLocating(null);
    }
  };

  return (
    <div className="space-y-3">
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <ListShell {...list} onPageChange={list.setPage} emptyText="还没有证据片段。">
        {list.items.map((span) => (
          <div key={span.id} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
            <blockquote className="border-l-4 border-primary/40 pl-3 text-sm text-slate-700">
              {span.excerpt}
            </blockquote>
            <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
              <span>
                文档 #{span.document_id} · 区块 #{span.block_id} · 字符 {span.char_start}–{span.char_end}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="rounded-full"
                disabled={locating === span.id}
                onClick={() => openInViewer(span.id)}
              >
                在原文中查看
              </Button>
            </div>
          </div>
        ))}
      </ListShell>
    </div>
  );
}
