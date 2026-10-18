"use client";

import { useCallback, useEffect, useState } from "react";
import { KnowledgeListResponse } from "@/types/knowledge";

export const PAGE_SIZE = 20;

export function usePagedList<T>(
  fetcher: (page: number, pageSize: number, q?: string) => Promise<KnowledgeListResponse<T>>,
  query?: string
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetcher(page, PAGE_SIZE, query || undefined);
      setItems(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [fetcher, page, query]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    setPage(1);
  }, [query]);

  return { items, total, page, setPage, loading, error, reload };
}
