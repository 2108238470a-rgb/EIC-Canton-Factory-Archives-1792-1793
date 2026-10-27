"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw, FileText, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ragApi } from "@/lib/api";
import { IndexDocument } from "@/types/rag";

export function IndexStatusBar({ onUpdated }: { onUpdated?: () => void }) {
  const [documents, setDocuments] = useState<IndexDocument[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);
  const load = useCallback(async () => {
    try {
      const r = await ragApi.documents();
      if (mounted.current) {
        setDocuments(r.items);
        setLoaded(true);
      }
    } catch (e) {
      if (mounted.current) setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    load();
    return () => {
      mounted.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [load]);
  function poll(id: string) {
    timer.current = setTimeout(async () => {
      try {
        const job = await ragApi.getIndexJob(id);
        if (!mounted.current) return;
        if (job.state === "SUCCESS") {
          setProgress(null);
          await load();
          onUpdated?.();
          if (job.info?.vector_failed)
            setError(
              "关键词索引已可用，部分语义索引未完成，可重新勾选文件重试。",
            );
        } else if (job.state === "FAILURE") {
          setProgress(null);
          setError(job.info?.error || "索引失败，请重试");
        } else {
          setProgress(
            job.info?.total
              ? `当前文件 ${job.info.done || 0}/${job.info.total} 个片段 · 已完成 ${job.info.documents_done || 0}/${job.info.documents_total || selected.length} 份 PDF`
              : "任务已排队，请稍候…",
          );
          poll(id);
        }
      } catch (e) {
        if (mounted.current) {
          setProgress(null);
          setError(
            `进度查询中断，任务可能仍在后台运行：${(e as Error).message}`,
          );
        }
      }
    }, 3000);
  }
  async function start() {
    setError("");
    setProgress("正在提交…");
    try {
      const job = await ragApi.startIndex(selected);
      poll(job.task_id);
    } catch (e) {
      setProgress(null);
      setError((e as Error).message);
    }
  }
  const visible = documents.filter((d) =>
    d.title.toLowerCase().includes(filter.toLowerCase()),
  );
  return (
    <section className="panel mb-5 overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-4 p-4 text-left sm:px-5"
      >
        <span className="flex items-center gap-3">
          <span className="rounded-md bg-primary/10 p-2 text-primary">
            <FileText className="h-4 w-4" />
          </span>
          <span>
            <span className="block text-sm font-medium">检索文献索引</span>
            <span className="mt-1 block text-xs text-muted-foreground">
              {loaded
                ? `${documents.filter((d) => d.indexed > 0).length} 份 PDF 可检索 · ${documents.length} 份包含 OCR 文本`
                : "正在读取文献…"}
            </span>
          </span>
        </span>
        <span className="flex items-center gap-2 text-xs text-primary">
          选择 PDF 更新索引
          <ChevronDown
            className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`}
          />
        </span>
      </button>
      {open && (
        <div className="border-t p-5">
          <p className="mb-4 text-xs leading-6 text-muted-foreground">
            勾选需要加入或更新的 PDF。只处理所选文件；部分完成 OCR
            的文件仅收录已有文本。完成后，请在下方选择检索范围。
          </p>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <input
              aria-label="筛选可索引PDF"
              className="field-control min-w-0 flex-1"
              placeholder="按文件名查找 PDF…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={!!progress || !visible.length}
              onClick={() =>
                setSelected(
                  Array.from(
                    new Set([...selected, ...visible.map((d) => d.id)]),
                  ),
                )
              }
            >
              勾选当前列表
            </Button>
            <button
              className="text-xs text-muted-foreground underline"
              disabled={!!progress}
              onClick={() => setSelected([])}
            >
              清空
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto overscroll-contain rounded-md border">
            {visible.map((d) => (
              <label
                key={d.id}
                className="flex cursor-pointer items-start gap-3 border-b p-3 last:border-0 hover:bg-muted/40"
              >
                <input
                  type="checkbox"
                  className="mt-1 accent-primary"
                  checked={selected.includes(d.id)}
                  disabled={!!progress}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, d.id]
                        : selected.filter((id) => id !== d.id),
                    )
                  }
                />
                <span className="min-w-0 flex-1">
                  <span className="block break-all text-sm">
                    {d.title}{" "}
                    <span className="text-xs text-muted-foreground">
                      · #{d.id}
                    </span>
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    OCR 文本覆盖 {d.ocr_pages}/{d.page_count} 页 · 已索引{" "}
                    {d.indexed}/{d.eligible} 个区块
                    {d.ocr_pages < d.page_count ? " · 部分 OCR" : ""}
                  </span>
                </span>
                <span className="status-badge">
                  {d.indexed === 0
                    ? "未建立索引"
                    : d.indexed < d.eligible
                      ? "待更新"
                      : "可检索"}
                </span>
              </label>
            ))}
            {!visible.length && (
              <p className="empty-state">
                {loaded ? "没有匹配的已 OCR PDF" : "读取中…"}
              </p>
            )}
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              已勾选 {selected.length} 份 PDF
            </span>
            <Button
              size="sm"
              disabled={!!progress || !selected.length}
              onClick={start}
            >
              {progress ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              更新所选 PDF 的索引
            </Button>
          </div>
        </div>
      )}
      {progress && (
        <p className="border-t px-5 py-3 text-xs text-primary" role="status">
          {progress}
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
          <button
            className="ml-3 underline"
            onClick={() => {
              setError("");
              load();
            }}
          >
            刷新列表
          </button>
        </p>
      )}
    </section>
  );
}
