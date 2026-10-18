"use client";

import { Suspense, useEffect, useRef, useState, ReactNode } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Search,
  Plus,
  Send,
  Download,
  FileText,
  MessageSquare,
  Library,
  History,
  X,
  PanelLeft,
  ArrowUpRight,
  Loader2,
  SlidersHorizontal,
  BookOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { IndexStatusBar } from "@/components/rag/IndexStatusBar";
import { EvidenceContent } from "@/components/workbench/EvidenceDialog";
import { workbenchApi, request } from "@/lib/workbench";
import { ragApi } from "@/lib/api";
import { Answer, Evidence, Hit, Scope } from "@/types/workbench";
import { IndexDocument } from "@/types/rag";

type Turn = {
  id: string;
  question: string;
  answer?: Answer;
  error?: string;
  evidenceIds: number[];
};
type Conversation = {
  id: string;
  title: string;
  scope: Scope;
  all: boolean;
  turns: Turn[];
  updated: string;
};
const STORAGE = "canton-research-conversations-v1";
const uid = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
function parseScope(p: URLSearchParams): Scope {
  return {
    mode: p.get("mode") === "explore" ? "explore" : "verified",
    retrieval: (["keyword", "semantic", "hybrid"].includes(
      p.get("retrieval") || "",
    )
      ? p.get("retrieval")
      : "hybrid") as Scope["retrieval"],
    document_id: Number(p.get("document")) || undefined,
    document_ids: p
      .getAll("documents")
      .map(Number)
      .filter((n) => Number.isInteger(n) && n > 0),
    corpus_id: Number(p.get("corpus")) || undefined,
    date_start: p.get("from") || undefined,
    date_end: p.get("to") || undefined,
    entity_id: Number(p.get("entity")) || undefined,
    unit_type: p.get("type") || undefined,
  };
}
function fresh(scope: Scope, all: boolean): Conversation {
  return {
    id: uid(),
    title: "新对话",
    scope,
    all,
    turns: [],
    updated: new Date().toISOString(),
  };
}
function writeURL(scope: Scope, all: boolean, view: string, q = "") {
  const p = new URLSearchParams({
    view,
    mode: scope.mode,
    retrieval: scope.retrieval || "hybrid",
  });
  if (!all) p.set("range", "selected");
  if (q) p.set("q", q);
  for (const [key, value] of Object.entries({
    document: scope.document_id,
    corpus: scope.corpus_id,
    from: scope.date_start,
    to: scope.date_end,
    entity: scope.entity_id,
    type: scope.unit_type,
  }))
    if (value) p.set(key, String(value));
  for (const id of scope.document_ids || []) p.append("documents", String(id));
  window.history.replaceState(null, "", `/research?${p}`);
}
function ResearchWorkspace() {
  const urlParams = useSearchParams();
  const initial = useRef(new URLSearchParams(urlParams.toString()));
  const p = initial.current;
  const [conversation, setConversation] = useState<Conversation>(() =>
    fresh(
      parseScope(p),
      !p.has("document") &&
        !p.has("documents") &&
        p.get("range") !== "selected",
    ),
  );
  const [sessions, setSessions] = useState<Conversation[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [storageError, setStorageError] = useState("");
  const [documents, setDocuments] = useState<IndexDocument[]>([]);
  const [documentsLoaded, setDocumentsLoaded] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [corpora, setCorpora] = useState<Array<{ id: number; name: string }>>(
    [],
  );
  const [libraryTab, setLibraryTab] = useState<"documents" | "corpora">(
    "documents",
  );
  const [fileFilter, setFileFilter] = useState("");
  const [view, setView] = useState<"chat" | "search">(
    p.get("view") === "search" || p.has("q") ? "search" : "chat",
  );
  const [query, setQuery] = useState(p.get("q") || "");
  const [question, setQuestion] = useState(p.get("question") || "");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [exportTurns, setExportTurns] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [evidenceOnly, setEvidenceOnly] = useState(false);
  const [source, setSource] = useState<{
    label: string;
    evidence: Evidence[];
  } | null>(null);
  const [narrowSource, setNarrowSource] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1279px)");
    const update = () => setNarrowSource(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [indexOpen, setIndexOpen] = useState(false);
  const [tips, setTips] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const requestNo = useRef(0);
  const initialSearchDone = useRef(false);
  const scope = conversation.scope;
  const available = documents.filter(
    (d) => !scope.corpus_id || d.corpus_id === scope.corpus_id,
  );
  const checkedIds = conversation.all
    ? available.map((d) => d.id)
    : available
        .filter(
          (d) =>
            (scope.document_ids || []).includes(d.id) ||
            scope.document_id === d.id,
        )
        .map((d) => d.id);
  const effectiveScope: Scope = {
    ...scope,
    document_id: undefined,
    document_ids: checkedIds,
  };
  const noDocuments = !documentsLoaded || !checkedIds.length;
  const scopeLabel = `${checkedIds.length} 份文献 · ${available.filter((d) => checkedIds.includes(d.id)).reduce((n, d) => n + d.indexed, 0)} 个已索引区块`;
  const activeRef = useRef(conversation.id);
  activeRef.current = conversation.id;
  const busyRef = useRef(false);
  async function loadDocuments() {
    setCatalogError("");
    try {
      const r = await ragApi.documents();
      setDocuments(r.items.filter((d) => d.indexed > 0));
      setDocumentsLoaded(true);
    } catch (e) {
      setCatalogError((e as Error).message);
    }
  }
  useEffect(() => {
    loadDocuments();
    request<{ items: Array<{ id: number; name: string }> }>(
      "/workbench/corpora",
    )
      .then((r) => setCorpora(r.items))
      .catch((e) => setError(e.message));
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE) || "[]");
      if (Array.isArray(saved))
        setSessions(
          saved
            .filter(
              (s) =>
                typeof s.id === "string" &&
                typeof s.title === "string" &&
                s.scope &&
                Array.isArray(s.turns) &&
                s.turns.every(
                  (t: Turn) =>
                    typeof t.question === "string" &&
                    (!t.answer ||
                      (typeof t.answer.answer === "string" &&
                        Array.isArray(t.answer.citations) &&
                        Array.isArray(t.answer.claims) &&
                        Array.isArray(t.answer.warnings))),
                ),
            )
            .slice(0, 20),
        );
    } catch {
      setStorageError("本机历史记录无法读取；仍可继续提问与导出。");
    }
    setHydrated(true);
    return () => {
      requestNo.current++;
    };
  }, []);
  useEffect(() => {
    if (!hydrated || !conversation.turns.length) return;
    setSessions((prev) =>
      [conversation, ...prev.filter((s) => s.id !== conversation.id)].slice(
        0,
        20,
      ),
    );
  }, [conversation, hydrated]);
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(
        STORAGE,
        JSON.stringify(sessions, (key, value) =>
          ["revision_content", "raw_revision_content"].includes(key)
            ? undefined
            : value,
        ),
      );
    } catch {
      setStorageError("本机历史空间不足，请导出当前对话保存。");
    }
  }, [sessions, hydrated]);
  useEffect(() => {
    const el = scrollRef.current;
    if (el)
      el.scrollTo({
        top: conversation.turns.length ? el.scrollHeight : 0,
        behavior: "smooth",
      });
  }, [conversation.turns, asking]);
  useEffect(() => {
    if (documentsLoaded && !initialSearchDone.current) {
      initialSearchDone.current = true;
      if (p.get("q") && checkedIds.length) runSearch(p.get("q")!);
    }
  }, [documentsLoaded]);
  function changeScope(next: Partial<Scope>, all = conversation.all) {
    if (asking) return;
    const updated = { ...scope, ...next };
    if (conversation.turns.length && !question.trim())
      setQuestion(conversation.turns[conversation.turns.length - 1].question);
    requestNo.current++;
    setLoading(false);
    setHits(null);
    setSelected([]);
    setSource(null);
    setError("");
    setWarnings([]);
    setEvidenceOnly(false);
    setExportTurns([]);
    setConversation((prev) =>
      prev.turns.length
        ? fresh(updated, all)
        : { ...prev, scope: updated, all },
    );
    writeURL(updated, all, view);
  }
  function toggleDocument(id: number, checked: boolean) {
    changeScope(
      {
        document_id: undefined,
        document_ids: checked
          ? Array.from(new Set([...checkedIds, id]))
          : checkedIds.filter((i) => i !== id),
      },
      false,
    );
  }
  function newConversation() {
    if (asking) return;
    requestNo.current++;
    setConversation(fresh(scope, conversation.all));
    setExportTurns([]);
    setQuestion("");
    setSource(null);
    setError("");
    setView("chat");
    setLibraryOpen(false);
    writeURL(scope, conversation.all, "chat");
  }
  function restore(s: Conversation) {
    if (asking) return;
    requestNo.current++;
    setLoading(false);
    setHits(null);
    setSelected([]);
    setEvidenceOnly(false);
    setWarnings([]);
    setError("");
    setConversation(s);
    setExportTurns([]);
    setView("chat");
    setQuestion("");
    setSource(null);
    setLibraryOpen(false);
    writeURL(s.scope, s.all, "chat");
  }
  async function runSearch(q = query) {
    if (!q.trim() || noDocuments) return;
    const serial = ++requestNo.current;
    setLoading(true);
    setError("");
    setSelected([]);
    setWarnings([]);
    writeURL(scope, conversation.all, "search", q.trim());
    try {
      const r = await workbenchApi.search(q.trim(), effectiveScope);
      if (serial === requestNo.current) {
        setHits(r.items);
        setWarnings(r.warnings);
      }
    } catch (e) {
      if (serial === requestNo.current) setError((e as Error).message);
    } finally {
      if (serial === requestNo.current) setLoading(false);
    }
  }
  async function ask(e?: React.FormEvent) {
    e?.preventDefault();
    if (
      !question.trim() ||
      busyRef.current ||
      noDocuments ||
      (evidenceOnly && !selected.length)
    )
      return;
    busyRef.current = true;
    setAsking(true);
    setError("");
    const text = question.trim(),
      id = uid(),
      sessionId = conversation.id;
    const previous = conversation.turns
      .filter((t) => t.answer && !t.answer.insufficient_evidence)
      .slice(-6)
      .map((t) => ({
        question: t.question,
        answer: t.answer!.answer.slice(0, 6000),
      }));
    writeURL(effectiveScope, false, "chat");
    setConversation((prev) => ({
      ...prev,
      scope: effectiveScope,
      all: false,
      title: prev.turns.length ? prev.title : text.slice(0, 45),
      turns: [
        ...prev.turns,
        { id, question: text, evidenceIds: evidenceOnly ? [...selected] : [] },
      ],
      updated: new Date().toISOString(),
    }));
    setQuestion("");
    try {
      const answer = await workbenchApi.ask(
        text,
        effectiveScope,
        evidenceOnly ? selected : [],
        previous,
      );
      if (activeRef.current === sessionId)
        setConversation((prev) => ({
          ...prev,
          turns: prev.turns.map((t) => (t.id === id ? { ...t, answer } : t)),
          updated: new Date().toISOString(),
        }));
    } catch (e) {
      if (activeRef.current === sessionId)
        setConversation((prev) => ({
          ...prev,
          turns: prev.turns.map((t) =>
            t.id === id ? { ...t, error: (e as Error).message } : t,
          ),
        }));
    } finally {
      busyRef.current = false;
      setAsking(false);
    }
  }
  function exportConversation(format: "json" | "md") {
    const turns = exportTurns.length
      ? conversation.turns.filter((t) => exportTurns.includes(t.id))
      : conversation.turns;
    const payload = {
      ...conversation,
      turns,
      exported_at: new Date().toISOString(),
      note: "对话的本机存档。历史引用可能因原文更新而需要重新核对。",
    };
    const text =
      format === "json"
        ? JSON.stringify(payload, null, 2)
        : `# ${conversation.title}\n\n文献 ID：${(scope.document_ids?.length ? scope.document_ids : checkedIds).join(", ")}\n内容状态：${scope.mode === "verified" ? "仅已复核" : "含待审文本"}\n\n` +
          turns
            .map(
              (t) =>
                `## 问：${t.question}\n\n${t.answer?.answer || t.error || "尚未生成回答"}\n\n` +
                (t.answer?.citations || [])
                  .map(
                    (c) =>
                      `[${c.index}] ${c.document_title} · PDF ${c.page_number}\n${new URL(c.viewer_path, window.location.origin)}\n${c.evidence.map((e) => `- 证据 ${e.public_id} · 文本版本 ${e.revision_id}\n  > ${e.excerpt}`).join("\n")}\n`,
                  )
                  .join("\n"),
            )
            .join("\n---\n\n");
    const url = URL.createObjectURL(
      new Blob([text], {
        type:
          format === "json"
            ? "application/json;charset=utf-8"
            : "text/markdown;charset=utf-8",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `档案研究对话-${new Date().toISOString().slice(0, 10)}.${format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function inlineAnswer(text: string, answer: Answer): ReactNode {
    return text.split(/(\[\d+\])/g).map((part, i) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (!match) return part;
      const c = answer.citations.find(
        (c) => c.index === Number(match[1]) && c.cited,
      );
      return c ? (
        <button
          key={i}
          className="inline-citation"
          aria-label={`查看引用 ${c.index}`}
          onClick={() =>
            setSource({
              label: `引用 [${c.index}] · ${c.document_title}`,
              evidence: c.evidence,
            })
          }
        >
          {part}
        </button>
      ) : (
        part
      );
    });
  }
  const library = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b p-4">
        <div className="mb-4 flex gap-1 rounded-lg bg-muted p-1">
          {[
            ["documents", "文献"],
            ["corpora", "专题库"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={`flex-1 rounded-md px-3 py-2 text-xs ${libraryTab === key ? "bg-card font-medium shadow-sm" : "text-muted-foreground"}`}
              onClick={() => setLibraryTab(key as "documents" | "corpora")}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="relative block">
          <Search className="absolute left-3 top-3 h-3.5 w-3.5 text-muted-foreground" />
          <input
            className="field-control w-full pl-9"
            aria-label="搜索文献或专题库"
            placeholder="搜索文献或专题库…"
            value={fileFilter}
            onChange={(e) => setFileFilter(e.target.value)}
          />
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <details className="border-b">
          <summary className="flex cursor-pointer items-center gap-2 p-4 text-xs font-medium">
            <History className="h-3.5 w-3.5" />
            历史会话
            <span className="ml-auto text-[10px] font-normal text-muted-foreground">
              本机 · {sessions.length}
            </span>
          </summary>
          <div className="max-h-60 overflow-auto px-2 pb-3">
            {sessions.length ? (
              sessions.map((s) => (
                <button
                  key={s.id}
                  disabled={asking}
                  onClick={() => restore(s)}
                  className={`mb-1 block w-full rounded-md px-3 py-2 text-left text-xs leading-5 ${s.id === conversation.id ? "bg-primary/10 text-primary" : "hover:bg-muted"}`}
                >
                  <span className="line-clamp-2">{s.title}</span>
                  <span className="mt-1 block text-[10px] text-muted-foreground">
                    {s.turns.length} 轮对话 ·{" "}
                    {new Date(s.updated).toLocaleDateString("zh-CN")}
                  </span>
                </button>
              ))
            ) : (
              <p className="px-3 py-2 text-xs leading-6 text-muted-foreground">
                提问后自动保存于当前浏览器，可随时导出。
              </p>
            )}
          </div>
        </details>
        {libraryTab === "documents" ? (
          <div>
            <div className="flex items-center justify-between px-4 pt-4 text-xs font-medium">
              <span className="flex items-center gap-2">
                <FileText className="h-3.5 w-3.5" />
                文献范围
              </span>
              <button
                disabled={asking}
                className="font-normal text-muted-foreground underline"
                onClick={() =>
                  changeScope(
                    {
                      document_id: undefined,
                      document_ids: [],
                      corpus_id: undefined,
                    },
                    false,
                  )
                }
              >
                清空
              </button>
            </div>
            <label className="mx-2 mt-3 flex items-center gap-3 rounded-md p-2 text-xs">
              <input
                type="checkbox"
                disabled={asking || !documentsLoaded}
                checked={conversation.all && !scope.corpus_id}
                onChange={(e) =>
                  changeScope(
                    {
                      document_id: undefined,
                      document_ids: [],
                      corpus_id: undefined,
                    },
                    e.target.checked,
                  )
                }
              />
              全部已索引文献
            </label>
            {scope.corpus_id && (
              <button
                className="mx-4 mt-2 text-xs text-primary"
                disabled={asking}
                onClick={() => changeScope({ corpus_id: undefined })}
              >
                移除专题库筛选 ×
              </button>
            )}
            <div className="space-y-1 p-2">
              {available
                .filter((d) =>
                  d.title.toLowerCase().includes(fileFilter.toLowerCase()),
                )
                .map((d) => (
                  <label
                    key={d.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg p-3 ${checkedIds.includes(d.id) ? "bg-primary/[.06]" : "hover:bg-muted/60"}`}
                  >
                    <input
                      type="checkbox"
                      className="mt-1 accent-primary"
                      disabled={asking}
                      checked={checkedIds.includes(d.id)}
                      onChange={(e) => toggleDocument(d.id, e.target.checked)}
                    />
                    <span className="min-w-0">
                      <span className="line-clamp-3 break-words text-xs leading-5">
                        {d.title}
                      </span>
                      <span className="mt-1.5 block text-[10px] text-muted-foreground">
                        #{d.id} · {d.page_count} 页 · {d.indexed} 区块
                      </span>
                    </span>
                  </label>
                ))}
            </div>
            {!documentsLoaded ? (
              <p className="empty-state">读取文献…</p>
            ) : !available.length ? (
              <p className="px-5 py-6 text-xs leading-6 text-muted-foreground">
                暂无可检索文献。请在右上角“管理索引”中勾选已 OCR 的 PDF。
              </p>
            ) : !available.some((d) =>
                d.title.toLowerCase().includes(fileFilter.toLowerCase()),
              ) ? (
              <p className="empty-state">没有匹配的文献</p>
            ) : null}
          </div>
        ) : (
          <div className="p-3">
            <p className="mb-3 px-1 text-xs leading-6 text-muted-foreground">
              选一个专题，围绕其中已索引文献提问。
            </p>
            {corpora
              .filter((c) =>
                c.name.toLowerCase().includes(fileFilter.toLowerCase()),
              )
              .map((c) => (
                <button
                  key={c.id}
                  disabled={asking}
                  className={`mb-2 flex w-full items-start gap-3 rounded-lg border p-3 text-left ${scope.corpus_id === c.id ? "border-primary/30 bg-primary/5" : "hover:bg-muted"}`}
                  onClick={() =>
                    changeScope(
                      {
                        corpus_id: c.id,
                        document_id: undefined,
                        document_ids: [],
                      },
                      true,
                    )
                  }
                >
                  <Library className="mt-1 h-4 w-4 shrink-0 text-primary" />
                  <span className="text-xs leading-6">
                    {c.name}
                    <span className="block text-[10px] text-muted-foreground">
                      {documents.filter((d) => d.corpus_id === c.id).length}{" "}
                      份可检索文献
                    </span>
                  </span>
                </button>
              ))}
            {!corpora.length && (
              <p className="px-1 text-xs leading-6 text-muted-foreground">
                尚未建立专题库。可在阅读器的“档案信息”中将文献归入集合。
              </p>
            )}
          </div>
        )}
      </div>
      <Link
        href="/documents"
        className="flex shrink-0 items-center justify-between border-t px-5 py-4 text-xs text-muted-foreground"
      >
        前往档案库管理文献
        <ArrowUpRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
  return (
    <div className="research-assistant">
      <aside className="research-library hidden min-h-0 flex-col border-r lg:flex">
        {library}
      </aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="assistant-toolbar">
          <div className="flex min-w-0 items-center gap-3">
            <button
              className="lg:hidden"
              aria-label="选择文献与历史会话"
              onClick={() => setLibraryOpen(true)}
            >
              <PanelLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-base font-semibold">AI 文献助手</h1>
              <p className="mt-1 text-[11px] text-muted-foreground">
                {scopeLabel} ·{" "}
                {scope.mode === "verified" ? "仅已复核" : "探索模式"}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={asking}
              onClick={newConversation}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              新对话
            </Button>
            <details className="relative">
              <summary className="flex h-9 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-xs">
                <Download className="h-3.5 w-3.5" />
                <span>
                  导出
                  {exportTurns.length
                    ? `所选 ${exportTurns.length} 轮`
                    : "对话"}
                </span>
              </summary>
              <div className="absolute right-0 top-11 z-20 w-40 rounded-lg border bg-card p-1 shadow-sm">
                <button
                  disabled={!conversation.turns.length || asking}
                  className="block w-full p-2 text-left text-xs disabled:opacity-40"
                  onClick={() => exportConversation("md")}
                >
                  Markdown（含引用）
                </button>
                <button
                  disabled={!conversation.turns.length || asking}
                  className="block w-full p-2 text-left text-xs disabled:opacity-40"
                  onClick={() => exportConversation("json")}
                >
                  JSON（含证据 ID）
                </button>
              </div>
            </details>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setIndexOpen(!indexOpen)}
              aria-expanded={indexOpen}
            >
              管理索引
            </Button>
            <Button
              size="icon"
              variant="ghost"
              aria-label="使用指南"
              onClick={() => setTips(!tips)}
            >
              <BookOpen className="h-4 w-4" />
            </Button>
          </div>
        </header>
        {indexOpen && (
          <p className="border-b px-5 py-2 text-xs text-muted-foreground">
            勾选 PDF 后更新索引；任务提交后可继续使用下方工作区。
          </p>
        )}
        <div
          className={
            indexOpen
              ? "max-h-[45vh] shrink-0 overflow-auto border-b p-4"
              : "hidden"
          }
        >
          <IndexStatusBar onUpdated={loadDocuments} />
        </div>
        {tips && (
          <div className="assistant-guide">
            <strong>① 勾选左侧文献</strong>
            <span>② 输入问题或检索原文</span>
            <span>③ 点击回答中的 [1] 核对原文与页图</span>
            <button
              className="ml-auto"
              aria-label="关闭指南"
              onClick={() => setTips(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="assistant-modebar">
          <div className="flex gap-5">
            {[
              ["chat", "文献对话", MessageSquare],
              ["search", "全文检索", Search],
            ].map(([key, label, Icon]) => {
              const I = Icon as typeof Search;
              return (
                <button
                  key={String(key)}
                  aria-current={view === key ? "page" : undefined}
                  onClick={() => {
                    setView(key as "chat" | "search");
                    writeURL(
                      scope,
                      conversation.all,
                      String(key),
                      key === "search" ? query : "",
                    );
                  }}
                  className="flex items-center gap-2 border-b-2 border-transparent py-3 text-xs text-muted-foreground aria-[current=page]:border-primary aria-[current=page]:font-medium aria-[current=page]:text-primary"
                >
                  <I className="h-3.5 w-3.5" />
                  {String(label)}
                </button>
              );
            })}
          </div>
          <details className="scope-settings">
            <summary className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              检索设置
            </summary>
            <div className="scope-settings-content">
              <label>
                <span className="field-label">内容范围</span>
                <select
                  className="field-control w-full"
                  disabled={asking}
                  value={scope.mode}
                  onChange={(e) =>
                    changeScope({ mode: e.target.value as Scope["mode"] })
                  }
                >
                  <option value="verified">仅已人工复核</option>
                  <option value="explore">探索：包含待审 OCR</option>
                </select>
              </label>
              <label>
                <span className="field-label">检索方式</span>
                <select
                  className="field-control w-full"
                  disabled={asking}
                  value={scope.retrieval}
                  onChange={(e) =>
                    changeScope({
                      retrieval: e.target.value as Scope["retrieval"],
                    })
                  }
                >
                  <option value="hybrid">关键词 + 语义</option>
                  <option value="keyword">关键词与精确名称</option>
                  <option value="semantic">语义检索</option>
                </select>
              </label>
              <div className="grid grid-cols-2 gap-3">
                {[
                  ["date_start", "文书日期起"],
                  ["date_end", "文书日期止"],
                ].map(([key, label]) => (
                  <label key={key}>
                    <span className="field-label">{label}</span>
                    <input
                      type="date"
                      className="field-control w-full"
                      disabled={asking}
                      value={scope[key as "date_start" | "date_end"] || ""}
                      onChange={(e) =>
                        changeScope({ [key]: e.target.value || undefined })
                      }
                    />
                  </label>
                ))}
              </div>
              <label>
                <span className="field-label">文书类型</span>
                <select
                  className="field-control w-full"
                  disabled={asking}
                  value={scope.unit_type || ""}
                  onChange={(e) =>
                    changeScope({ unit_type: e.target.value || undefined })
                  }
                >
                  <option value="">全部类型</option>
                  {[
                    ["letter_incoming", "来函"],
                    ["letter_outgoing", "复函"],
                    ["diary_entry", "日记"],
                    ["meeting_minutes", "会议记录"],
                    ["report", "报告"],
                    ["other", "其他"],
                  ].map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="field-label">人物／实体 ID（可选）</span>
                <input
                  className="field-control w-full"
                  type="number"
                  min="1"
                  disabled={asking}
                  value={scope.entity_id || ""}
                  onChange={(e) =>
                    changeScope({
                      entity_id: Number(e.target.value) || undefined,
                    })
                  }
                />
              </label>
              <p className="text-[11px] leading-5 text-muted-foreground">
                日期和类型依据文书元数据；修改文献或设置将开始新对话，旧对话保留在本机历史中。
              </p>
            </div>
          </details>
        </div>
        {catalogError && (
          <div className="error-message my-2" role="alert">
            文献列表加载失败：{catalogError}
            <button className="ml-3 underline" onClick={loadDocuments}>
              重试加载
            </button>
          </div>
        )}
        {storageError && (
          <p className="px-5 py-2 text-xs text-amber-800" role="status">
            {storageError}
          </p>
        )}
        {error && (
          <p className="error-message my-2" role="alert">
            {error}
          </p>
        )}
        <div className="flex min-h-0 flex-1">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div
              ref={scrollRef}
              className="assistant-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain"
            >
              {view === "chat" ? (
                <div className="assistant-transcript">
                  {!conversation.turns.length ? (
                    <div className="assistant-welcome">
                      <div className="welcome-icon">
                        <MessageSquare className="h-6 w-6" />
                      </div>
                      <p className="eyebrow">READ · ASK · VERIFY</p>
                      <h2>
                        让每一次提问，
                        <br />
                        都能回到原始文献。
                      </h2>
                      <p className="mt-5 max-w-lg text-sm leading-7 text-muted-foreground">
                        选择一份档案或一个专题，围绕原文提问、比较与追问。
                        <br className="hidden sm:block" />
                        点击回答中的引用，即可对照引句和原始页图。
                      </p>
                      <div className="welcome-prompts">
                        {[
                          "概括这些文献中的主要人物与事件",
                          "比较不同来源对同一事件的记载",
                          "这封信中的请求由谁提出，又由谁转达？",
                        ].map((q) => (
                          <button key={q} onClick={() => setQuestion(q)}>
                            {q}
                            <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
                          </button>
                        ))}
                      </div>
                      <button
                        className="mt-6 text-xs text-primary lg:hidden"
                        onClick={() => setLibraryOpen(true)}
                      >
                        选择文献范围 →
                      </button>
                    </div>
                  ) : (
                    conversation.turns.map((t) => (
                      <article key={t.id} className="conversation-turn">
                        <div className="user-question">{t.question}</div>
                        <div className="assistant-answer">
                          <div className="mb-4 flex items-center justify-between">
                            <span className="flex items-center gap-2 text-xs font-medium text-primary">
                              <BookOpen className="h-4 w-4" />
                              档案研究助手
                            </span>
                            <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
                              <input
                                type="checkbox"
                                aria-label={`选择导出问题：${t.question}`}
                                checked={exportTurns.includes(t.id)}
                                onChange={(e) =>
                                  setExportTurns(
                                    e.target.checked
                                      ? [...exportTurns, t.id]
                                      : exportTurns.filter((id) => id !== t.id),
                                  )
                                }
                              />
                              导出
                            </label>
                          </div>
                          {t.answer ? (
                            <>
                              {t.answer.insufficient_evidence && (
                                <div className="notice mb-4">
                                  <p>
                                    {t.answer.outcome === "invalid_citations"
                                      ? "已检索到原文，但回答未通过引用校验。这不代表 OCR 没有识别出内容。"
                                      : t.answer.outcome === "model_unavailable"
                                        ? "回答服务暂不可用，原文证据仍可核对。"
                                        : t.answer.outcome === "model_timeout"
                                          ? "本轮回答生成超时，原文证据已保留，可缩小文献范围后重试。"
                                          : t.answer.outcome === "stale_sources"
                                            ? "原文已更新，请重新检索。"
                                            : "当前筛选范围暂不足以支撑回答。OCR 完成、校正完成与人工复核是不同状态。"}
                                  </p>
                                  {scope.mode === "verified" &&
                                    ![
                                      "invalid_citations",
                                      "model_unavailable",
                                      "model_timeout",
                                      "stale_sources",
                                    ].includes(t.answer.outcome || "") && (
                                      <button
                                        className="mt-2 underline"
                                        disabled={asking}
                                        onClick={() =>
                                          changeScope({ mode: "explore" })
                                        }
                                      >
                                        使用待审 OCR 重新准备本问题 →
                                      </button>
                                    )}
                                </div>
                              )}
                              {t.answer.outcome === "extractive_overview" && (
                                <p className="notice mb-4">
                                  原文线索整理：以下保留可核对的姓名与主题线索，尚未形成完整的模型分析。
                                </p>
                              )}
                              <div className="answer-prose">
                                {t.answer.sections?.length
                                  ? t.answer.sections.map((section, i) => (
                                      <section
                                        key={i}
                                        className="mb-6 last:mb-0"
                                      >
                                        <h3 className="mb-3 border-b border-border pb-2 text-base font-semibold text-foreground">
                                          {section.title}
                                        </h3>
                                        {section.content
                                          .split(/\n\n+/)
                                          .map((part, j) => (
                                            <p key={j}>
                                              {inlineAnswer(part, t.answer!)}
                                            </p>
                                          ))}
                                      </section>
                                    ))
                                  : t.answer.answer
                                      .split(/\n\n+/)
                                      .map((part, i) => (
                                        <p key={i}>
                                          {inlineAnswer(part, t.answer!)}
                                        </p>
                                      ))}
                              </div>
                              {t.answer.warnings.map((w) => (
                                <p className="notice mt-3" key={w}>
                                  {w}
                                </p>
                              ))}
                              {t.answer.citations.length > 0 && (
                                <div className="answer-sources">
                                  <p className="mb-2 text-[11px] text-muted-foreground">
                                    {t.answer.insufficient_evidence
                                      ? "可供核对的检索片段"
                                      : "原文来源 · 点击核对"}
                                  </p>
                                  {t.answer.citations.map((c) => (
                                    <button
                                      key={c.chunk_id}
                                      className="source-chip"
                                      onClick={() =>
                                        setSource({
                                          label: `${c.cited ? "引用" : "片段"} [${c.index}] · ${c.document_title}`,
                                          evidence: c.evidence,
                                        })
                                      }
                                    >
                                      <span>[{c.index}]</span>
                                      <span className="min-w-0 truncate">
                                        {c.document_title}
                                      </span>
                                      <span className="shrink-0 text-muted-foreground">
                                        第 {c.page_number} 页
                                      </span>
                                    </button>
                                  ))}
                                </div>
                              )}
                              {t.answer.claims.length > 0 && (
                                <details className="mt-4 text-xs">
                                  <summary className="cursor-pointer text-muted-foreground">
                                    查看逐字引句与判断依据
                                  </summary>
                                  {t.answer.claims.map((claim, i) => (
                                    <div
                                      key={i}
                                      className="mt-3 border-l pl-3 leading-6"
                                    >
                                      <p>{claim.text}</p>
                                      {claim.quotes.map((q, j) => (
                                        <blockquote
                                          key={j}
                                          className="text-muted-foreground"
                                        >
                                          [{claim.citations[j]}] {q}
                                        </blockquote>
                                      ))}
                                    </div>
                                  ))}
                                </details>
                              )}
                              <p className="mt-5 text-[10px] leading-5 text-muted-foreground">
                                {t.evidenceIds.length
                                  ? `仅使用所选 ${t.evidenceIds.length} 个片段。`
                                  : "已在本轮文献范围中重新检索。"}
                                引用可核对来源，历史解释仍需研究者判断。历史回答不代表引用始终有效。
                              </p>
                            </>
                          ) : t.error ? (
                            <div>
                              <p className="notice" role="alert">
                                {t.error}
                              </p>
                              <button
                                className="mt-3 text-xs text-primary"
                                onClick={() => setQuestion(t.question)}
                              >
                                将问题放回输入框重试 →
                              </button>
                            </div>
                          ) : asking ? (
                            <p
                              className="flex items-center gap-2 text-sm text-muted-foreground"
                              role="status"
                            >
                              <Loader2 className="h-4 w-4 animate-spin" />
                              正在检索原文、核对引用…
                            </p>
                          ) : (
                            <p className="text-xs text-muted-foreground">
                              上次请求尚未完成，可重新输入该问题。
                            </p>
                          )}
                        </div>
                      </article>
                    ))
                  )}
                </div>
              ) : (
                <div className="search-workspace">
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      runSearch();
                    }}
                    className="flex gap-2"
                  >
                    <input
                      aria-label="检索词"
                      className="field-control min-w-0 flex-1"
                      placeholder="人名、地名、原文关键词或研究主题…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                    <Button
                      disabled={
                        noDocuments || loading || asking || !query.trim()
                      }
                    >
                      {loading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Search className="h-4 w-4" />
                      )}
                      <span className="ml-2">检索</span>
                    </Button>
                  </form>
                  <div className="my-4 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span>
                      {hits
                        ? `${hits.length} 个相关片段`
                        : "在左侧所选文献中检索"}{" "}
                      · 已选 {selected.length}/20
                    </span>
                    {selected.length > 0 && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setView("chat");
                          setEvidenceOnly(true);
                          writeURL(scope, conversation.all, "chat");
                        }}
                      >
                        基于所选证据提问 →
                      </Button>
                    )}
                  </div>
                  {warnings.map((w) => (
                    <p className="notice mb-3" key={w}>
                      {w}
                    </p>
                  ))}
                  {loading ? (
                    <p className="empty-state" role="status">
                      正在检索原文…
                    </p>
                  ) : hits === null ? (
                    <div className="search-empty">
                      <Search className="h-8 w-8" />
                      <h2>从一个关键词开始</h2>
                      <p>原文与译文共同检索，结果保留文本版本与页块定位。</p>
                    </div>
                  ) : !hits.length ? (
                    <p className="empty-state">
                      当前范围没有匹配片段。请调整关键词、文献或审核状态；未检索到并不代表历史上不存在。
                    </p>
                  ) : (
                    hits.map((h) => (
                      <article key={h.chunk_id} className="evidence-result">
                        <div className="flex items-start gap-3">
                          <input
                            aria-label={`选择证据：${h.document_title} 第 ${h.page_number} 页`}
                            type="checkbox"
                            className="mt-1 accent-primary"
                            checked={selected.includes(h.chunk_id)}
                            disabled={
                              asking ||
                              (!selected.includes(h.chunk_id) &&
                                selected.length >= 20)
                            }
                            onChange={(e) =>
                              setSelected(
                                e.target.checked
                                  ? [...selected, h.chunk_id]
                                  : selected.filter((id) => id !== h.chunk_id),
                              )
                            }
                          />
                          <div className="min-w-0 flex-1">
                            <h3 className="break-words text-sm font-medium">
                              {h.document_title}
                            </h3>
                            <p className="mt-1.5 text-[11px] text-muted-foreground">
                              第 {h.page_number} 页 ·{" "}
                              {h.review_state === "approved"
                                ? "已复核"
                                : "待审文本"}{" "}
                              ·{" "}
                              {h.content_type === "source_paragraph"
                                ? "文书段落"
                                : "临时区块片段"}
                            </p>
                          </div>
                        </div>
                        <p className="my-4 whitespace-pre-wrap text-sm leading-7">
                          {h.content}
                        </p>
                        <div className="flex gap-4 text-xs text-primary">
                          <button
                            onClick={() =>
                              setSource({
                                label: `第 ${h.page_number} 页 · ${h.document_title}`,
                                evidence: h.evidence,
                              })
                            }
                          >
                            查看原文与页图
                          </button>
                          <Link href={h.viewer_path}>打开阅读器 ↗</Link>
                        </div>
                      </article>
                    ))
                  )}
                  {hits && (
                    <p className="mt-4 text-[10px] leading-6 text-muted-foreground">
                      按相关性返回片段，不代表档案中的全部记录。关键词检索可独立于语义服务工作。
                    </p>
                  )}
                </div>
              )}
            </div>
            {view === "chat" && (
              <footer className="assistant-composer">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>
                    {evidenceOnly
                      ? `仅所选 ${selected.length} 个证据片段`
                      : scopeLabel}
                  </span>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={evidenceOnly}
                      disabled={asking}
                      onChange={(e) => setEvidenceOnly(e.target.checked)}
                    />
                    仅使用所选证据
                  </label>
                </div>
                <form onSubmit={ask} className="composer-input">
                  <textarea
                    id="research-question"
                    aria-label="研究问题"
                    rows={2}
                    maxLength={1000}
                    placeholder={
                      noDocuments
                        ? "请先选择已索引文献…"
                        : "向所选文献提问，或继续追问…"
                    }
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        ask();
                      }
                    }}
                  />
                  <button
                    type="submit"
                    aria-label="发送问题"
                    disabled={
                      asking ||
                      noDocuments ||
                      !question.trim() ||
                      (evidenceOnly && !selected.length)
                    }
                  >
                    {asking ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                  </button>
                </form>
                <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
                  {noDocuments
                    ? "请在文献列表勾选文件；清空选择不会自动改为全库。"
                    : evidenceOnly && !selected.length
                      ? "请先在“全文检索”勾选证据，或取消“仅使用所选证据”。"
                      : "Enter 发送 · Shift + Enter 换行。追问参考最近 6 轮；更换文献范围会开始新对话。"}
                </p>
              </footer>
            )}
          </div>
          {source && (
            <aside className="source-preview hidden min-h-0 flex-col border-l xl:flex">
              <div className="flex items-start justify-between gap-3 border-b p-4">
                <div>
                  <h2 className="text-sm font-semibold">返回引用原文</h2>
                  <p className="mt-2 line-clamp-2 text-[11px] leading-5 text-muted-foreground">
                    {source.label}
                  </p>
                </div>
                <button
                  aria-label="关闭原文侧栏"
                  onClick={() => setSource(null)}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 space-y-7 overflow-auto overscroll-contain p-4">
                {source.evidence.length ? (
                  source.evidence.map((e) => (
                    <EvidenceContent key={e.id} evidence={e} />
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    该片段暂无可展示的证据定位，请通过阅读器核对。
                  </p>
                )}
              </div>
            </aside>
          )}
        </div>
      </main>
      <Dialog.Root open={libraryOpen} onOpenChange={setLibraryOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[65] bg-foreground/25" />
          <Dialog.Content className="fixed bottom-0 left-0 top-0 z-[66] flex w-[min(340px,90vw)] flex-col border-r bg-card">
            <div className="flex justify-between border-b p-4">
              <Dialog.Title className="text-sm font-semibold">
                文献与历史会话
              </Dialog.Title>
              <Dialog.Description className="sr-only">
                选择本轮研究文献或恢复本机历史。
              </Dialog.Description>
              <Dialog.Close aria-label="关闭文献列表">
                <X className="h-4 w-4" />
              </Dialog.Close>
            </div>
            {library}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <Dialog.Root
        open={Boolean(source) && narrowSource}
        onOpenChange={(open) => {
          if (!open) setSource(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[65] bg-foreground/25 xl:hidden" />
          <Dialog.Content className="fixed bottom-0 right-0 top-0 z-[66] flex w-[min(520px,100vw)] flex-col border-l bg-card xl:hidden">
            <div className="flex items-center justify-between gap-3 border-b p-4">
              <div>
                <Dialog.Title className="text-sm font-semibold">
                  返回引用原文
                </Dialog.Title>
                <Dialog.Description className="mt-2 text-xs text-muted-foreground">
                  {source?.label}
                </Dialog.Description>
              </div>
              <Dialog.Close aria-label="关闭引用原文">
                <X className="h-4 w-4" />
              </Dialog.Close>
            </div>
            <div className="min-h-0 flex-1 space-y-7 overflow-auto p-4">
              {source?.evidence.map((e) => (
                <EvidenceContent key={e.id} evidence={e} />
              ))}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
export default function ResearchPage() {
  return (
    <Suspense fallback={<p className="empty-state">加载文献助手…</p>}>
      <ResearchWorkspace />
    </Suspense>
  );
}
