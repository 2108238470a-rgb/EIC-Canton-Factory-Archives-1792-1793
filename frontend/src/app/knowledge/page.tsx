"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ResearchWorkflow } from "@/components/workbench/ResearchWorkflow";
import { AnnotationTable } from "@/components/workbench/AnnotationTable";
import { Annotation, Paged, STATE_LABELS } from "@/types/workbench";
import { documentApi } from "@/lib/api";
import { Document } from "@/types";
import { apiUrl, request, workbenchApi } from "@/lib/workbench";
interface Item {
  id: number;
  canonical_name?: string;
  title?: string;
  entity_type?: string;
  status?: string;
}
export default function KnowledgePage() {
  const [tab, setTab] = useState("annotations");
  const [documentId, setDocumentId] = useState("");
  const [documents, setDocuments] = useState<Document[]>([]);
  useEffect(() => {
    documentApi
      .list(1, 100)
      .then((r) => setDocuments(r.items))
      .catch((e) => setError(e.message));
  }, []);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<Annotation[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const params = new URLSearchParams({
    page: String(page),
    page_size: "20",
    ...(query ? { q: query } : {}),
    ...(status ? { status } : {}),
    ...(documentId && tab === "annotations" ? { document_id: documentId } : {}),
  });
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const params = new URLSearchParams({
      page: String(page),
      page_size: "20",
      ...(query ? { q: query } : {}),
      ...(status ? { status } : {}),
      ...(documentId && tab === "annotations"
        ? { document_id: documentId }
        : {}),
    });
    const load =
      tab === "annotations"
        ? workbenchApi.annotations(params)
        : request<Paged<Item>>(
            `/workbench/${tab === "events" ? "events" : "entities"}?${params}&entity_type=${tab === "events" ? "" : tab}`,
          );
    load
      .then((result) => {
        if (!active) return;
        setTotal(result.total);
        if (tab === "annotations") setRows(result.items as Annotation[]);
        else setItems(result.items as Item[]);
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [tab, query, status, page, documentId]);
  return (
    <div className="app-shell py-8">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Historical knowledge</p>
          <h1 className="section-title">知识库</h1>
          <p className="section-description mt-2">
            从原文记载到研究判断，每条知识保留来源与审核历史。
          </p>
        </div>
        <Link href="/documents">
          <Button>从档案建立标注</Button>
        </Link>
      </div>
      <ResearchWorkflow current="knowledge" />
      <nav className="section-tabs" aria-label="知识类型">
        {[
          ["annotations", "标注总表"],
          ["person", "人物"],
          ["organization", "机构"],
          ["place", "地点"],
          ["events", "事件"],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => {
              setTab(key);
              setPage(1);
            }}
            aria-current={tab === key ? "page" : undefined}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="panel">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(q.trim());
              setPage(1);
            }}
          >
            <Input
              aria-label="搜索知识"
              placeholder="名称、原文形式或事件"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <Button variant="outline">搜索</Button>
          </form>
          <div className="flex flex-wrap gap-2">
            {tab === "annotations" && (
              <>
                <select
                  aria-label="档案范围"
                  className="field-control max-w-[250px]"
                  value={documentId}
                  onChange={(e) => {
                    setDocumentId(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">全部档案</option>
                  {documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.original_filename}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="审核状态"
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value);
                    setPage(1);
                  }}
                  className="field-control"
                >
                  <option value="">全部审核状态</option>
                  {["pending", "approved", "rejected", "needs_validation"].map(
                    (s) => (
                      <option key={s} value={s}>
                        {STATE_LABELS[s]}
                      </option>
                    ),
                  )}
                </select>
                {["csv", "json", "zip"].map((f) => (
                  <a
                    key={f}
                    className="text-xs px-2 py-2 text-primary underline"
                    href={apiUrl(
                      `/api/v2/workbench/exports?${params}&format=${f}`,
                    )}
                  >
                    {f === "zip" ? "证据包" : f.toUpperCase()}
                  </a>
                ))}
              </>
            )}
          </div>
        </div>
        {error ? (
          <p className="error-message" role="alert">
            {error}
          </p>
        ) : loading ? (
          <p className="empty-state" role="status">
            正在加载知识记录…
          </p>
        ) : tab === "annotations" ? (
          <AnnotationTable items={rows} />
        ) : items.length ? (
          <div className="divide-y">
            {items.map((i) => (
              <Link
                key={i.id}
                className="flex justify-between p-5 hover:bg-muted/40"
                href={`/knowledge/${tab === "events" ? "events" : "dossiers"}/${i.id}`}
              >
                <span>{i.canonical_name || i.title}</span>
                <span className="text-sm text-muted-foreground">
                  {STATE_LABELS[i.status || ""] || "查看档案"} →
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            暂无记录。审核标注中的人物或事件字段后，相关档案将出现在这里。
          </div>
        )}
        <div className="flex items-center justify-between border-t p-4 text-sm">
          <span>
            共 {total} 条{tab === "annotations" ? "标注" : "记录"}
          </span>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 1 || loading}
              onClick={() => setPage(page - 1)}
            >
              上一页
            </Button>
            <span>{page}</span>
            <Button
              variant="outline"
              size="sm"
              disabled={page * 20 >= total || loading}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
