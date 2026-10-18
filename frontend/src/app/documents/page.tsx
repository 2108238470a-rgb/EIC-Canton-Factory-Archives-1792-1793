"use client";

import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { documentApi } from "@/lib/api";
import { Document } from "@/types";
import { formatFileSize, formatDate, getStatusText } from "@/lib/utils";
import {
  FileText,
  ArrowUpRight,
  Trash2,
  Loader2,
  RefreshCw,
  RotateCcw,
  Plus,
  Search,
  X,
} from "lucide-react";
import { ProcessingStatus } from "@/components/workbench/ProcessingStatus";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [archived, setArchived] = useState(false);
  const [filter, setFilter] = useState("");
  const [remove, setRemove] = useState<Document | null>(null);
  const [busy, setBusy] = useState(false);
  const pageSize = 20;
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await documentApi.list(page, pageSize, archived);
      setDocuments(r.items);
      setTotal(r.total);
      if (!r.items.length && page > 1) setPage(page - 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [page, archived]);
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);
  async function move(doc: Document, restore = false) {
    setBusy(true);
    setError("");
    try {
      if (restore) await documentApi.restore(doc.id);
      else await documentApi.delete(doc.id);
      setRemove(null);
      setMessage(
        restore
          ? "文档已恢复，可继续阅读与检索。"
          : "已移入回收站。原文件、标注和引用均保留，可随时恢复。",
      );
      await fetchDocuments();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visible = documents.filter((d) =>
    d.original_filename.toLowerCase().includes(filter.toLowerCase()),
  );
  return (
    <div className="app-shell py-9 md:py-12">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Archive collection</p>
          <h1 className="section-title">你的档案，研究的起点。</h1>
          <p className="section-description mt-3">
            整理史料、对照原图，在阅读中留下可以追溯的证据。
          </p>
        </div>
        <Link href="/upload">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            导入档案
          </Button>
        </Link>
      </div>
      <div className="collection-toolbar">
        <nav aria-label="档案视图" className="flex gap-6">
          <button
            aria-current={!archived ? "page" : undefined}
            onClick={() => {
              setArchived(false);
              setPage(1);
              setMessage("");
            }}
          >
            全部档案 {!archived && <span>{total}</span>}
          </button>
          <button
            aria-current={archived ? "page" : undefined}
            onClick={() => {
              setArchived(true);
              setPage(1);
              setMessage("");
            }}
          >
            回收站 {archived && <span>{total}</span>}
          </button>
        </nav>
        <div className="flex items-center gap-2">
          <label className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              className="field-control w-full pl-9 sm:w-60"
              aria-label="筛选本页档案"
              placeholder="筛选本页文件名"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </label>
          <Button
            aria-label="刷新列表"
            size="icon"
            variant="ghost"
            onClick={fetchDocuments}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>
      {archived && (
        <p className="mb-5 text-sm leading-7 text-muted-foreground">
          回收站中的文档不参与检索。已有引用仍可打开，恢复后重新进入档案库。
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="success-message mb-5" role="status">
          {message}
        </p>
      )}
      <section
        className="collection-list"
        aria-label={archived ? "回收站文档" : "档案列表"}
      >
        {loading ? (
          <div className="empty-state flex items-center justify-center gap-3">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在读取档案…
          </div>
        ) : visible.length ? (
          visible.map((doc, index) => (
            <article key={doc.id} className="collection-row">
              <div className="archive-number">
                {String((page - 1) * pageSize + index + 1).padStart(2, "0")}
              </div>
              <div className="min-w-0 flex-1">
                <Link href={`/documents/${doc.id}`} className="archive-title">
                  {doc.original_filename}
                </Link>
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
                  <span>
                    {doc.file_type.toUpperCase()} · {doc.page_count} 页
                  </span>
                  <span>{formatFileSize(doc.file_size)}</span>
                  <span>{formatDate(doc.created_at)}</span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <span className="processing-status">
                    {getStatusText(doc.status)}
                  </span>
                  <ProcessingStatus document={doc} />
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {archived ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => move(doc, true)}
                  >
                    <RotateCcw className="mr-2 h-3.5 w-3.5" />
                    恢复
                  </Button>
                ) : (
                  <>
                    <Link href={`/viewer/${doc.id}`}>
                      <Button size="sm" variant="outline">
                        阅读 <ArrowUpRight className="ml-2 h-3.5 w-3.5" />
                      </Button>
                    </Link>
                    <Button
                      aria-label={`将 ${doc.original_filename} 移入回收站`}
                      size="icon"
                      variant="ghost"
                      onClick={() => setRemove(doc)}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </>
                )}
              </div>
            </article>
          ))
        ) : (
          <div className="empty-state">
            <FileText className="mx-auto mb-4 h-7 w-7" />
            {filter
              ? "本页没有匹配的文件。"
              : archived
                ? "回收站是空的。"
                : "还没有档案，从导入一份史料开始。"}
          </div>
        )}
      </section>
      {total > pageSize && (
        <div className="mt-7 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            第 {page} / {Math.ceil(total / pageSize)} 页 · 共 {total} 份文档
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 1 || loading}
              onClick={() => setPage(page - 1)}
            >
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page * pageSize >= total || loading}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </Button>
          </div>
        </div>
      )}
      {remove && (
        <Dialog.Root
          open
          onOpenChange={(open) => {
            if (!open && !busy) setRemove(null);
          }}
        >
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-[70] bg-foreground/30" />
            <Dialog.Content
              role="alertdialog"
              className="fixed left-1/2 top-1/2 z-[71] w-[calc(100%-2.5rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-card p-6 shadow-lg"
              onEscapeKeyDown={(e) => {
                if (busy) e.preventDefault();
              }}
              onPointerDownOutside={(e) => {
                if (busy) e.preventDefault();
              }}
            >
              <div className="flex items-center justify-between">
                <Dialog.Title className="text-lg font-semibold">
                  移入回收站？
                </Dialog.Title>
                <button
                  disabled={busy}
                  aria-label="取消移入回收站"
                  onClick={() => setRemove(null)}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <p className="my-4 break-all text-sm font-medium">
                {remove.original_filename}
              </p>
              <Dialog.Description className="text-sm leading-7 text-muted-foreground">
                文档将从档案库和检索范围中移除。原文件、研究标注和已有引用都会保留，你可以在回收站恢复。
              </Dialog.Description>
              {error && (
                <p className="error-message m-0 mt-3" role="alert">
                  {error}
                </p>
              )}
              <div className="mt-6 flex justify-end gap-3">
                <Button
                  autoFocus
                  variant="outline"
                  disabled={busy}
                  onClick={() => setRemove(null)}
                >
                  取消
                </Button>
                <Button disabled={busy} onClick={() => move(remove)}>
                  {busy ? "正在移动…" : "移入回收站"}
                </Button>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      )}
    </div>
  );
}
