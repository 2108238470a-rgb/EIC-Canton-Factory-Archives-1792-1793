"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  BookOpen,
  ChevronRight,
  Download,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  FileText,
  Clock3,
  ArrowUpRight,
  Search,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { request, apiUrl } from "@/lib/workbench";
import { pageApi } from "@/lib/api";

type Source = {
  revision_id: number;
  block_id: number;
  page_id: number;
  page_number: number;
  page_label?: string;
  text_type: string;
  review_status: string;
  quote: string;
  char_start: number;
  char_end: number;
  bbox: number[];
};
type Item = {
  id: string;
  title: string;
  description?: string;
  kind?: string;
  toc_type?: string;
  origin?: string;
  level?: number;
  page_start?: number;
  page_end?: number;
  date?: string;
  date_basis?: string;
  review_status: string;
  people?: string[];
  organizations?: string[];
  sources: Source[];
};
type Artifact = {
  summary?: { id: string; text: string; sources: Source[] }[];
  stage?: string;
  summary_progress?: { level: number; next_group: number; total_groups: number };
  current_batch?: number;
  batch_started_at?: string;
  toc: Item[];
  items: Item[];
  errors: { batch: number; message: string }[];
  completed_batches: number;
  total_batches: number;
  covered_characters: number;
  total_characters: number;
  text_pages: number;
  text_blocks: number;
  revision: number;
};
type Run = {
  id: number;
  document_id: number;
  status: string;
  stale: boolean;
  model: string;
  created_at: string;
  error?: string;
  artifact: Artifact;
  parameters: { mode: string; parent_run_id?: number; analysis_profile?: string };
};
type Workspace = {
  document_id: number;
  title: string;
  page_count: number;
  text_pages: number;
  text_blocks: number;
  runs: { id: number; status: string; mode: string; created_at: string }[];
  latest: Run | null;
};
const statuses: Record<string, string> = {
  pending: "等待分析",
  running: "分析中",
  completed: "已完成",
  failed: "分析失败",
  cancelled: "已取消",
};
const types: Record<string, string> = {
  ocr_raw: "原始 OCR",
  ocr_corrected: "AI 纠错文本",
  manual_transcription: "人工转录",
};
const basis: Record<string, string> = {
  event_explicit: "原文明确的事件日期",
  document_explicit: "文书落款日期",
  unknown: "日期未确定",
};

function Separator({
  value,
  onChange,
  label,
  min,
  max,
  invert = false,
}: {
  value: number;
  onChange: (n: number) => void;
  label: string;
  min: number;
  max: number;
  invert?: boolean;
}) {
  const start = useRef({ x: 0, value: 0 });
  const clamp = (n: number) => Math.max(min, Math.min(max, n));
  return (
    <div
      role="separator"
      tabIndex={0}
      aria-label={label}
      aria-orientation="vertical"
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      className="workspace-resizer"
      onPointerDown={(e) => {
        start.current = { x: e.clientX, value };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId))
          onChange(
            clamp(
              start.current.value +
                (e.clientX - start.current.x) * (invert ? -1 : 1),
            ),
          );
      }}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          e.preventDefault();
          onChange(
            clamp(
              value + (e.key === "ArrowRight" ? 12 : -12) * (invert ? -1 : 1),
            ),
          );
        }
      }}
    />
  );
}

export default function DocumentWorkspace() {
  const id = Number(useParams().id);
  const [data, setData] = useState<Workspace | null>(null),
    [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [tab, setTab] = useState("overview"),
    [tocType, setTocType] = useState("pages"),
    [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Item | null>(null),
    [sourceIndex, setSourceIndex] = useState(0),
    [left, setLeft] = useState(248),
    [right, setRight] = useState(340);
  const [editTitle, setEditTitle] = useState("");
  const evidenceRef = useRef<HTMLElement>(null);
  const load = useCallback(async () => {
    try {
      const result = await request<Workspace>(`/insights/documents/${id}`);
      setData(result);
      setRun(result.latest);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);
  useEffect(() => {
    load();
    setSelected(null);
  }, [load]);
  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("eic-workspace-widths") || "null",
      );
      if (saved) {
        setLeft(Math.max(190, Math.min(380, saved.left || 248)));
        setRight(Math.max(260, Math.min(480, saved.right || 340)));
      }
    } catch {}
  }, []);
  useEffect(() => {
    localStorage.setItem(
      "eic-workspace-widths",
      JSON.stringify({ left, right }),
    );
  }, [left, right]);
  useEffect(() => {
    if (!run || !["pending", "running"].includes(run.status)) return;
    const timer = setInterval(() => {
      request<Run>(`/insights/runs/${run.id}`)
        .then((updated) => {
          setRun(updated);
          setData((previous) =>
            previous
              ? {
                  ...previous,
                  runs: previous.runs.map((r) =>
                    r.id === updated.id ? { ...r, status: updated.status } : r,
                  ),
                }
              : previous,
          );
        })
        .catch((e) => setError(e.message));
    }, 2500);
    return () => clearInterval(timer);
  }, [run?.id, run?.status]);
  async function act(path: string, body?: unknown, method = "POST") {
    setBusy(true);
    setError("");
    try {
      const result = await request<Run>(path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      setRun(result);
      setSelected(null);
      setEditTitle("");
      const fresh = await request<Workspace>(`/insights/documents/${id}`);
      setData(fresh);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function choose(item: Item) {
    setSelected(item);
    setSourceIndex(0);
    setEditTitle(item.title);
    if (window.innerWidth < 801)
      setTimeout(
        () =>
          evidenceRef.current?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          }),
        20,
      );
  }
  if (loading)
    return (
      <div className="app-shell py-10" aria-busy="true">
        <div className="h-7 w-2/3 animate-pulse rounded bg-muted" />
        <div className="mt-8 h-64 animate-pulse rounded bg-muted" />
      </div>
    );
  if (!data)
    return (
      <div className="app-shell py-10">
        <p role="alert" className="error-message">
          {error}
        </p>
        <Button onClick={load}>重新连接</Button>
      </div>
    );
  const artifact = run?.artifact;
  const active = !!run && ["pending", "running"].includes(run.status);
  const items = artifact?.items || [];
  const topics = items.filter((i) => i.kind === "topic");
  const directory =
    tocType === "historical_topic"
      ? topics
      : tocType === "chronological"
        ? items
            .filter((i) => !!i.date)
            .sort((a, b) => a.date!.localeCompare(b.date!))
        : (artifact?.toc || []).filter((i) => i.toc_type === tocType);
  const filtered = directory.filter((i) =>
    `${i.title} ${i.description || ""}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const events = items.filter((i) => i.kind === "event");
  const dated = events
    .filter((i) => i.date && i.date_basis === "event_explicit")
    .sort((a, b) => a.date!.localeCompare(b.date!));
  const uncertain = events.filter(
    (i) => !i.date || i.date_basis !== "event_explicit",
  );
  const source = selected?.sources[sourceIndex];
  const progress = artifact?.total_batches
    ? Math.round((100 * artifact.completed_batches) / artifact.total_batches)
    : 0;
  const readerPath = (s: Source) =>
    `/viewer/${id}?page=${s.page_number}&block=${s.block_id}`;
  const fact = (item: Item) => (
    <button
      className="research-fact"
      key={item.id}
      onClick={() => choose(item)}
    >
      <div className="flex items-start justify-between gap-3">
        <h4>{item.title}</h4>
        <ChevronRight size={15} className="shrink-0 text-muted-foreground" />
      </div>
      <p>{item.description}</p>
      <div className="mt-2 text-[11px] text-primary">
        {item.sources.map((s) => `第 ${s.page_number} 页`).join(" · ")} · AI
        候选，待核实
      </div>
    </button>
  );
  return (
    <div className="document-workspace archive-studio">
      <header className="document-workspace-head">
        <Link
          href="/documents"
          className="mb-3 inline-flex items-center gap-2 text-xs text-muted-foreground"
        >
          <ArrowLeft size={13} />
          我的文献 / 研究工作区
        </Link>
        <div className="document-workspace-title">
          <div className="min-w-0">
            <h1>{data.title}</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {data.page_count} 页 · {data.text_pages} 页有文本 ·{" "}
              {data.text_blocks} 个文本区块 {run ? `· 分析版本 #${run.id}` : ""}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Link href={`/viewer/${id}`}>
              <Button variant="outline" size="sm">
                <BookOpen size={14} className="mr-2" />
                原文对照
              </Button>
            </Link>
            <Button
              size="sm"
              disabled={busy || active || !data.text_blocks}
              onClick={() =>
                act(`/insights/documents/${id}`, { mode: "ai", force: !!run })
              }
            >
              {busy ? (
                <Loader2 size={14} className="mr-2 animate-spin" />
              ) : (
                <Play size={14} className="mr-2" />
              )}
              {run?.parameters.mode === "ai" ? "重新分析" : "生成智能分析"}
            </Button>
          </div>
        </div>
        <nav className="document-tabs" aria-label="文献视图">
          {[
            ["overview", "文献概览"],
            ["toc", "智能目录"],
            ["timeline", "事件时间线"],
          ].map(([key, label]) => (
            <button
              key={key}
              aria-current={tab === key ? "page" : undefined}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
          <Link href={`/research?documents=${id}&mode=explore`}>文献问答</Link>
          <Link href={`/documents/${id}`}>处理与导出</Link>
        </nav>
      </header>
      {error && (
        <p role="alert" className="error-message mx-4 mt-3">
          {error}
          <button className="ml-3 underline" onClick={() => setError("")}>
            关闭
          </button>
        </p>
      )}
      <div className="document-workspace-body">
        <aside
          className="document-directory"
          style={{ width: left }}
          aria-label="文献目录"
        >
          <h2>
            文献导航{" "}
            <span className="ml-2 text-muted-foreground">CONTENTS</span>
          </h2>
          <select
            className="field-control mb-3 w-full"
            aria-label="目录类型"
            value={tocType}
            onChange={(e) => setTocType(e.target.value)}
          >
            <option value="pages">页码临时目录</option>
            <option value="original">原始文书目录</option>
            <option value="historical_topic">AI 主题目录</option>
            <option value="chronological">时间目录（含文书日期）</option>
          </select>
          <label className="mb-3 flex items-center gap-2 rounded border bg-card px-2">
            <Search size={14} />
            <input
              aria-label="搜索目录"
              placeholder="搜索目录…"
              className="min-w-0 w-full bg-transparent py-2 text-xs outline-none"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          {!run ? (
            <div className="text-xs leading-7 text-muted-foreground">
              先建立页码导航，再选择是否生成 AI 分析。
              <Button
                className="mt-3 w-full"
                variant="outline"
                size="sm"
                disabled={busy || !data.text_blocks}
                onClick={() =>
                  act(`/insights/documents/${id}`, { mode: "directory" })
                }
              >
                建立基础目录
              </Button>
            </div>
          ) : null}
          {run && !filtered.length && (
            <p className="px-2 py-4 text-xs leading-6 text-muted-foreground">
              {search
                ? "未找到匹配条目。"
                : tocType === "original"
                  ? "尚无已定位的文书分段，可先使用页码目录。"
                  : tocType === "pages"
                    ? "没有可用的页码条目。"
                    : "尚无此类分析条目。生成智能分析后在此查看。"}
            </p>
          )}
          {tocType === "pages" && !search
            ? Array.from(
                new Set(
                  filtered.map((i) =>
                    Math.floor(((i.page_start || 1) - 1) / 20),
                  ),
                ),
              ).map((group, index) => (
                <details
                  key={group}
                  open={
                    index === 0 ||
                    !!selected?.sources.some(
                      (s) => Math.floor((s.page_number - 1) / 20) === group,
                    )
                  }
                  className="mb-2"
                >
                  <summary className="cursor-pointer px-2 py-2 text-xs font-medium text-muted-foreground">
                    第 {group * 20 + 1}–
                    {Math.min((group + 1) * 20, data.page_count)} 页
                  </summary>
                  {filtered
                    .filter(
                      (i) =>
                        Math.floor(((i.page_start || 1) - 1) / 20) === group,
                    )
                    .map((i) => (
                      <div key={i.id} className="flex items-start pl-2">
                        <button
                          className="directory-row"
                          data-active={selected?.id === i.id}
                          onClick={() => choose(i)}
                        >
                          <span>{i.title}</span>
                          <small>{i.page_start}</small>
                        </button>
                        <Link
                          className="px-1 py-3 text-xs text-primary"
                          aria-label={`打开原文：${i.title}`}
                          href={readerPath(i.sources[0])}
                        >
                          ↗
                        </Link>
                      </div>
                    ))}
                </details>
              ))
            : filtered.map((i) => (
                <div key={i.id} className="flex items-start">
                  <button
                    className="directory-row"
                    data-active={selected?.id === i.id}
                    onClick={() => choose(i)}
                  >
                    <ChevronRight size={12} className="shrink-0" />
                    <span>
                      {tocType === "chronological" ? `${i.date} · ` : ""}
                      {i.title}
                    </span>
                    <small>{i.page_start || i.sources[0]?.page_number}</small>
                  </button>
                  <Link
                    className="px-1 py-3 text-xs text-primary"
                    aria-label={`打开原文：${i.title}`}
                    href={readerPath(i.sources[0])}
                  >
                    ↗
                  </Link>
                </div>
              ))}
        </aside>
        <Separator
          value={left}
          onChange={setLeft}
          label="调整目录宽度"
          min={190}
          max={380}
        />
        <main className="workspace-content">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="eyebrow !mb-0">
              DOCUMENT RESEARCH /{" "}
              {tab === "overview"
                ? "OVERVIEW"
                : tab === "toc"
                  ? "CONTENTS"
                  : "TIMELINE"}
            </p>
            {run && (
              <select
                aria-label="历史分析版本"
                className="field-control max-w-[230px]"
                value={run.id}
                onChange={(e) => {
                  request<Run>(`/insights/runs/${e.target.value}`)
                    .then((r) => {
                      setRun(r);
                      setSelected(null);
                    })
                    .catch((e) => setError(e.message));
                }}
              >
                {data.runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    #{r.id} · {statuses[r.status]} ·{" "}
                    {r.mode === "ai" ? "AI分析" : "基础目录"}
                  </option>
                ))}
              </select>
            )}
          </div>
          <section className="workspace-intro">
            <div className="workspace-cover">
              {artifact?.toc[0]?.sources[0] ? (
                <img
                  src={pageApi.getImageUrl(artifact.toc[0].sources[0].page_id)}
                  alt="当前档案封面"
                />
              ) : (
                <BookOpen size={44} strokeWidth={1} />
              )}
              <span>PRIMARY SOURCE</span>
            </div>
            <div className="workspace-intro-copy">
              <span className="studio-kicker">
                <span /> HISTORICAL RESEARCH · 文献 #{id}
              </span>
              <h2>
                {tab === "overview"
                  ? "文献研究概览"
                  : tab === "toc"
                    ? "文献目录与主题"
                    : "历史事件时间线"}
              </h2>
              <p>
                梳理文献的脉络，追踪人物与事件。每一条研究线索，都保留回到原始档案的路径。
              </p>
              <div className="studio-metadata">
                <span>
                  <FileText size={13} />
                  {data.page_count} 页档案
                </span>
                <span>
                  <BookOpen size={13} />
                  {data.text_pages} 页可读文本
                </span>
                <span>
                  <Sparkles size={13} />
                  {events.length} 条候选事件
                </span>
              </div>
            </div>
          </section>
          {run && (
            <div className={`workspace-task task-${run.status}`} role="status">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong>
                  {run.stale ? (
                    "原文已变更 · 此分析需要重新生成"
                  ) : (
                    <>
                      <span className="task-status-dot" />
                      {statuses[run.status]}
                    </>
                  )}
                </strong>
                <span>
                  {artifact?.completed_batches || 0} /{" "}
                  {artifact?.total_batches || 0} 批 ·{" "}
                  {artifact?.stage === "aggregating"
                    ? `正在聚合全文概述${artifact.summary_progress ? ` · 第 ${artifact.summary_progress.level + 1} 层 · 已保存 ${artifact.summary_progress.next_group}/${artifact.summary_progress.total_groups} 组` : ""}`
                    : active
                      ? `正在读取第 ${artifact?.current_batch || (artifact?.completed_batches || 0) + 1} 批`
                      : run.parameters.mode === "ai"
                        ? "全文分批分析"
                        : "基础页码导航"}
                </span>
              </div>
              {run.parameters.mode === "ai" && (
                <>
                  <progress
                    className="mt-2 h-1.5 w-full accent-primary"
                    value={progress}
                    max={100}
                  />
                  <p>
                    已覆盖 {artifact?.covered_characters.toLocaleString()} /{" "}
                    {artifact?.total_characters.toLocaleString()} 字符。
                    {progress < 100
                      ? "当前显示阶段性线索，尚不能代表全文结论。"
                      : "已遍历本次全部文本区块；语义结论仍需人工核对。"}
                    {active &&
                      " 你可以离开此页，任务会在后台继续；再次打开即可查看进度。"}
                  </p>
                </>
              )}
              {run.parameters.mode === "ai" &&
                run.parameters.analysis_profile !== "compact-v2" && (
                  <p className="mt-2 text-muted-foreground">
                    此版本使用旧分析配置，单批较大、容易超时。建议用新版配置建立独立分析版本；旧线索和来源仍保留。
                  </p>
                )}
              {run.error && (
                <p className="mt-2 text-destructive">
                  {run.error === "TimeoutError"
                    ? `这一批的模型响应超时。前 ${artifact?.completed_batches || 0} 批结果已保留，可从未完成处继续。`
                    : run.error}
                </p>
              )}
              {active && (
                <Button
                  className="mt-2"
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => act(`/insights/runs/${run.id}/cancel`)}
                >
                  取消分析
                </Button>
              )}
              {["failed", "cancelled"].includes(run.status) && !run.stale && (
                <Button
                  className="mt-2"
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run.parameters.analysis_profile !== "compact-v2"
                      ? act(`/insights/documents/${id}`, { mode: "ai", force: true })
                      : act(`/insights/runs/${run.id}/retry`)
                  }
                >
                  <RefreshCw size={13} className="mr-2" />
                  {run.parameters.analysis_profile !== "compact-v2"
                    ? "用新版配置分析（保留旧记录）"
                    : "从失败位置继续"}
                </Button>
              )}
              <p className="mt-1 text-muted-foreground">
                {run.parameters.mode === "ai"
                  ? "候选分析不自动进入已核实知识库。"
                  : "基础目录依据真实页块与已有分段生成，不包含 AI 概括。"}
              </p>
            </div>
          )}
          {tab === "overview" && (
            <>
              <div className="workspace-kpis">
                <div>
                  <strong>{data.page_count}</strong>
                  <span>文献总页数</span>
                </div>
                <div>
                  <strong>{data.text_pages}</strong>
                  <span>有 OCR 文本的页数</span>
                </div>
                <div>
                  <strong>{topics.length}</strong>
                  <span>AI 主题线索</span>
                </div>
                <div>
                  <strong>{events.length}</strong>
                  <span>候选事件（当前分析版本）</span>
                </div>
              </div>
              {!items.length ? (
                <div className="workspace-empty">
                  <h3>
                    {run?.parameters.mode === "ai" && run.status === "completed"
                      ? "本轮未生成可核验的研究线索"
                      : "为这份文献建立研究概览"}
                  </h3>
                  <p>
                    {run?.parameters.mode === "ai" && run.status === "completed"
                      ? "模型已遍历本次输入，但没有返回带有效引句的线索。这不代表文献没有研究价值；可先核对原文质量与引用校验记录，再重新分析。系统不会补写没有依据的历史结论。"
                      : "生成智能分析后，可查看分段内容概述、主题目录、事件与研究方向。分析会使用当前配置的模型，按批次处理本份文献的全文文本；不需要重新 OCR。基础目录可以立即建立，AI 分析独立运行。"}
                  </p>
                  <p className="mt-3">
                    模型分析失败时，原文阅读、编辑与既有导出仍可使用。
                  </p>
                </div>
              ) : (
                <>
                  {!!artifact?.summary?.length && (
                    <section className="research-section">
                      <h3>全文内容概览 · AI 候选解释</h3>
                      {artifact.summary.map((paragraph, index) => (
                        <button
                          key={paragraph.id}
                          className="research-fact"
                          onClick={() =>
                            choose({
                              id: paragraph.id,
                              title: `全文概览 · 第 ${index + 1} 段`,
                              description: paragraph.text,
                              review_status: "unverified",
                              sources: paragraph.sources,
                            })
                          }
                        >
                          <p className="!text-foreground">{paragraph.text}</p>
                          <span className="mt-2 block text-[11px] text-primary">
                            核对 {paragraph.sources.length} 处原文引用 ↗
                          </span>
                        </button>
                      ))}
                    </section>
                  )}
                  {[
                    ["overview", "文献主要内容 · 分段证据概述"],
                    ["context", "与档案相关的背景解释 · AI 候选"],
                    ["direction", "潜在研究方向 · 待核实"],
                  ].map(([kind, title]) => (
                    <details
                      className="research-section research-notes"
                      key={kind}
                      open={kind === "overview" && !artifact?.summary?.length}
                    >
                      <summary>
                        {title}
                        <span>
                          {items.filter((i) => i.kind === kind).length} 条线索
                        </span>
                      </summary>
                      {items.filter((i) => i.kind === kind).map(fact)}
                      {!items.some((i) => i.kind === kind) && (
                        <p className="text-xs text-muted-foreground">
                          本轮未生成有引句支撑的内容。
                        </p>
                      )}
                    </details>
                  ))}
                  <section className="research-section">
                    <h3>重要历史线索</h3>
                    {events.slice(0, 10).map(fact)}
                    {!events.length && (
                      <p className="text-xs text-muted-foreground">
                        当前批次未提取到事件线索。
                      </p>
                    )}
                  </section>
                </>
              )}
            </>
          )}
          {tab === "toc" && (
            <section className="research-section">
              <h3>
                {tocType === "historical_topic"
                  ? "AI 重建主题目录"
                  : tocType === "original"
                    ? "已有文书分段目录"
                    : tocType === "pages"
                      ? "按实际文本页建立的临时目录"
                      : "按明确日期排列的线索目录"}
              </h3>
              <p className="mb-3 text-xs leading-6 text-muted-foreground">
                左侧切换目录类型。条目可核对出处、跳转原图及重命名；历史名称和原文不会随目录编辑改变。
              </p>
              {filtered.map(fact)}
            </section>
          )}
          {tab === "timeline" && (
            <section className="research-section">
              <h3>事件实际日期 · 原文明确记载</h3>
              {!dated.length && (
                <p className="mb-6 text-xs leading-7 text-muted-foreground">
                  尚无引句明确支持事件发生日期的线索。文书落款日期不会自动作为事件日期。
                </p>
              )}
              {dated.map((item) => (
                <div className="timeline-entry" key={item.id}>
                  <time>{item.date}</time>
                  {fact(item)}
                </div>
              ))}
              <h3 className="mt-6">日期待核实 / 仅有文书日期</h3>
              {uncertain.map(fact)}
              {!uncertain.length && (
                <p className="text-xs text-muted-foreground">
                  暂无未定日期的事件线索。
                </p>
              )}
            </section>
          )}
          {artifact && artifact.errors.length > 0 && (
            <details className="research-section text-xs">
              <summary>
                引用校验记录（{artifact.errors.length} 条未接纳内容）
              </summary>
              {artifact.errors.map((e, index) => (
                <p key={index} className="mt-2">
                  批次{e.batch}：{e.message}
                </p>
              ))}
            </details>
          )}
          {run && (
            <footer className="research-section">
              <h3>研究导出</h3>
              <div className="flex flex-wrap gap-3">
                {[
                  ["json", "JSON（含来源 manifest）"],
                  ["markdown", "Markdown 研究草稿"],
                ].map(([format, label]) => (
                  <a
                    key={format}
                    className="inline-flex items-center gap-2 text-xs text-primary underline"
                    href={apiUrl(
                      `/api/v2/insights/runs/${run.id}/export?format=${format}`,
                    )}
                  >
                    <Download size={13} />
                    {label}
                  </a>
                ))}
              </div>
              <p className="mt-3 text-xs leading-6 text-muted-foreground">
                保留候选状态、文本版本与覆盖率。分析版
                Word/PDF、复杂目录合并拆分和关系图尚未在本阶段提供。
              </p>
            </footer>
          )}
        </main>
        {selected && source && (
          <>
            <Separator
              value={right}
              onChange={setRight}
              label="调整来源面板宽度"
              min={260}
              max={480}
              invert
            />
            <aside
              ref={evidenceRef}
              className="evidence-pane"
              style={{ width: right }}
              aria-label="来源核验"
            >
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">来源核验</h2>
                <button aria-label="关闭来源" onClick={() => setSelected(null)}>
                  <X size={16} />
                </button>
              </div>
              <h3 className="mt-5 text-sm font-semibold leading-6">
                {selected.title}
              </h3>
              <p className="mt-2 text-xs text-muted-foreground">
                {selected.review_status === "approved"
                  ? "文书分段已复核"
                  : "研究线索 / 尚未核实"}
                {run?.stale ? " · 此分析已过时" : ""}
              </p>
              {selected.sources.length > 1 && (
                <select
                  className="field-control mt-3 w-full"
                  aria-label="来源引句"
                  value={sourceIndex}
                  onChange={(e) => setSourceIndex(Number(e.target.value))}
                >
                  {selected.sources.map((s, i) => (
                    <option key={i} value={i}>
                      第 {s.page_number} 页 · 区块 {s.block_id}
                    </option>
                  ))}
                </select>
              )}
              <Link
                href={readerPath(source)}
                className="mt-4 block overflow-hidden rounded border bg-card"
              >
                <img
                  key={source.page_id}
                  src={pageApi.getImageUrl(source.page_id)}
                  alt={`第${source.page_number}页扫描，打开阅读器定位区块`}
                  className="max-h-64 w-full object-contain"
                  loading="lazy"
                />
              </Link>
              <p className="mt-3 text-[11px] text-muted-foreground">
                第 {source.page_number} 页
                {source.page_label ? ` · 原档 ${source.page_label}` : ""} · 区块{" "}
                {source.block_id}
              </p>
              <blockquote>{source.quote}</blockquote>
              <dl className="space-y-2 text-[11px] text-muted-foreground">
                <div>
                  证据类型：{types[source.text_type] || source.text_type}
                </div>
                <div>
                  人工核实：
                  {source.review_status === "approved" ? "已核实" : "待核实"}
                </div>
                <div>
                  文本版本：#{source.revision_id} · 字符 {source.char_start}–
                  {source.char_end}
                </div>
                {selected.kind === "event" && (
                  <div>
                    日期：{selected.date || "未确定"} ·{" "}
                    {basis[selected.date_basis || "unknown"]}
                  </div>
                )}
              </dl>
              <Link
                href={readerPath(source)}
                className="mt-5 block text-xs font-medium text-primary underline"
              >
                在阅读器核对原图与文字 ↗
              </Link>
              <Link
                className="mt-4 block rounded border bg-primary px-3 py-2 text-center text-xs text-primary-foreground"
                href={`${readerPath(source)}&annotate_revision=${source.revision_id}&annotate_start=${source.char_start}&annotate_end=${source.char_end}&annotate_field=${source.text_type}`}
              >
                用这段引句记录研究判断 →
              </Link>
              <p className="mt-2 text-[11px] leading-6 text-muted-foreground">
                带入原文位置后补充人物或事件，保存为待审记录，再逐项审核。原始
                OCR 不会被覆盖。
              </p>
              {(selected.toc_type || selected.kind === "topic") && (
                <form
                  className="research-section"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (run)
                      act(
                        `/insights/runs/${run.id}/toc/${selected.id}`,
                        {
                          title: editTitle,
                          expected_revision: artifact?.revision,
                        },
                        "PATCH",
                      );
                  }}
                >
                  <label className="field-label" htmlFor="toc-title">
                    重命名目录（保留旧版本）
                  </label>
                  <input
                    id="toc-title"
                    className="field-control w-full"
                    value={editTitle}
                    maxLength={180}
                    onChange={(e) => setEditTitle(e.target.value)}
                  />
                  <Button
                    className="mt-3"
                    size="sm"
                    variant="outline"
                    disabled={
                      busy ||
                      run?.stale ||
                      run?.status !== "completed" ||
                      !editTitle.trim()
                    }
                  >
                    保存新修订
                  </Button>
                </form>
              )}
            </aside>
          </>
        )}
      </div>
    </div>
  );
}
