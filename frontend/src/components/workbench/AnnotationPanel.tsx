"use client";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Block, Page } from "@/types";
import { Evidence, Extraction, FIELD_LABELS } from "@/types/workbench";
import { request, workbenchApi } from "@/lib/workbench";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EvidenceDialog } from "./EvidenceDialog";
type TextField =
  "ocr_text_raw" | "ocr_text_corrected" | "modern_english" | "translation_zh";
interface Unit {
  id: number;
  title: string;
  segmentation_status: string;
  updated_at: string;
  spans: Array<{ block_id: number }>;
}
export function AnnotationPanel({
  block,
  documentId,
  page,
  onBlockUpdated,
}: {
  block: Block | null;
  documentId: number;
  page: Page | null;
  onBlockUpdated: (block: Block) => void;
}) {
  const searchParams = useSearchParams();
  const fromAnnotation = Number(searchParams.get("from_annotation")) || null;
  const [checkedCurrent, setCheckedCurrent] = useState(false);
  const [quality, setQuality] = useState<{
    ocr_warnings: string[];
    report: null | {
      accepted: boolean;
      candidate: string;
      edit_ratio: number | null;
      reasons: string[];
    };
  } | null>(null);
  useEffect(() => {
    let active = true;
    setQuality(null);
    if (block)
      request<{
        ocr_warnings: string[];
        report: null | {
          accepted: boolean;
          candidate: string;
          edit_ratio: number | null;
          reasons: string[];
        };
      }>(`/workbench/blocks/${block.id}/correction-quality`)
        .then((r) => {
          if (active) setQuality(r);
        })
        .catch(() => {});
    return () => {
      active = false;
    };
  }, [block?.id, block?.ocr_text_corrected]);
  const [correctionDraft, setCorrectionDraft] = useState("");
  useEffect(() => {
    setCorrectionDraft(block?.ocr_text_corrected || block?.ocr_text_raw || "");
  }, [block?.id, block?.ocr_text_corrected, block?.ocr_text_raw]);
  const [tab, setTab] = useState("annotate");
  const [textField, setTextField] = useState<TextField>("ocr_text_raw");
  const [range, setRange] = useState([0, 0]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [unitId, setUnitId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [run, setRun] = useState<Extraction | null>(null);
  const [pageStart, setPageStart] = useState("");
  const [pageEnd, setPageEnd] = useState("");
  const [forceNew, setForceNew] = useState(false);
  const [parts, setParts] = useState<Evidence[]>([]);
  const [unitTitle, setUnitTitle] = useState("");
  const [unitType, setUnitType] = useState("other");
  const [unitDate, setUnitDate] = useState("");
  const [unitOriginalDate, setUnitOriginalDate] = useState("");
  const [corpora, setCorpora] = useState<Array<{ id: number; name: string }>>(
    [],
  );
  const [corpusId, setCorpusId] = useState("");
  const [corpusName, setCorpusName] = useState("");
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [pageLabel, setPageLabel] = useState("");
  const [folioSide, setFolioSide] = useState("");
  const text = block?.[textField] || "";
  useEffect(() => {
    const field = block?.ocr_text_corrected
      ? "ocr_text_corrected"
      : "ocr_text_raw";
    setCheckedCurrent(false);
    setTextField(field);
    setRange([0, Array.from(block?.[field] || "").length]);
    setEvidence(null);
    setFields({});
    if (fromAnnotation)
      workbenchApi
        .annotation(fromAnnotation)
        .then((a) => {
          if (a.document_id !== documentId) return;
          setFields({
            ...a.fields,
            notes: [a.fields.notes, `重新核对标注 ${a.public_id}`]
              .filter(Boolean)
              .join("；"),
          });
          setMessage(
            "已带入原标注内容。请先在当前原文中选取引句，再检查下方字段并保存。",
          );
        })
        .catch((e) => setError(e.message));
    setMessage("");
    setError("");
  }, [block?.id, fromAnnotation, documentId]);
  useEffect(() => {
    setRange([0, Array.from(text).length]);
    setEvidence(null);
  }, [text, textField]);
  function loadUnits() {
    request<{ items: Unit[] }>(
      `/workbench/documents/${documentId}/source-units`,
    )
      .then((r) => setUnits(r.items))
      .catch((e) => setError(e.message));
  }
  useEffect(() => {
    loadUnits();
    request<{ items: Array<{ id: number; name: string }> }>(
      "/workbench/corpora",
    )
      .then((r) => setCorpora(r.items))
      .catch((e) => setError(e.message));
    request<Record<string, string>>(
      `/workbench/documents/${documentId}/metadata`,
    )
      .then((r) => {
        setMeta(r);
        setCorpusId(String(r.corpus_id || ""));
      })
      .catch((e) => setError(e.message));
  }, [documentId]);
  useEffect(() => {
    setPageLabel(
      (page as (Page & { original_page_label?: string }) | null)
        ?.original_page_label || "",
    );
    setFolioSide(
      (page as (Page & { folio_side?: string }) | null)?.folio_side || "",
    );
  }, [page]);
  useEffect(() => {
    if (!run || !["pending", "running"].includes(run.status)) return;
    let active = true;
    const id = setInterval(
      () =>
        workbenchApi
          .extraction(run.id)
          .then((r) => {
            if (active) setRun(r);
          })
          .catch((e) => {
            if (active) setError(e.message);
          }),
      2500,
    );
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [run?.id, run?.status]);
  async function action(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await task();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function makeEvidence() {
    if (!block) throw new Error("请先选择原文区块");
    const e = await workbenchApi.createEvidence({
      block_id: block.id,
      text_field: textField,
      expected_text: text,
      char_start: range[0],
      char_end: range[1],
    });
    setEvidence(e);
    return e;
  }
  const quote = Array.from(text).slice(range[0], range[1]).join("");
  return (
    <aside className="panel min-w-0 overflow-hidden">
      <nav
        className="section-tabs sticky top-0 z-10 mb-0 bg-card"
        aria-label="标注面板"
      >
        {[
          ["annotate", "标注"],
          ["segment", "文书分段"],
          ["metadata", "档案信息"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="space-y-4 p-4">
        {error && (
          <p className="error-message m-0" role="alert">
            {error}
          </p>
        )}
        {message && (
          <p
            className="rounded border border-primary/20 bg-primary/5 p-3 text-xs leading-6"
            role="status"
          >
            {message}
          </p>
        )}
        {tab !== "metadata" && (
          <>
            {block ? (
              <>
                <label className="field-label" htmlFor="evidence-layer">
                  证据文本层
                </label>
                <select
                  id="evidence-layer"
                  value={textField}
                  onChange={(e) => setTextField(e.target.value as TextField)}
                  className="field-control w-full"
                >
                  {[
                    ["ocr_text_raw", "原始 OCR"],
                    ["ocr_text_corrected", "校订原文"],
                    ["modern_english", "现代英语"],
                    ["translation_zh", "中文译文"],
                  ]
                    .filter(([key]) => Boolean(block[key as TextField]))
                    .map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                </select>
                {quality?.ocr_warnings.length ? (
                  <p className="notice">
                    OCR
                    存在重复生成或异常字符线索，请先对照页图。此提示不是识别正确率。
                  </p>
                ) : null}
                {quality?.report && !quality.report.accepted && (
                  <details className="notice">
                    <summary className="cursor-pointer font-medium">
                      有一份高风险校正候选，未自动写入
                    </summary>
                    <p className="mt-2">
                      涉及姓名、数字、否定词或改动过多，需要对照原图核验。变更比例{" "}
                      {quality.report.edit_ratio == null
                        ? "未计算（文本过长）"
                        : `${(quality.report.edit_ratio * 100).toFixed(1)}%`}
                      （不是 CER）。
                    </p>
                    <p className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded border bg-card p-3">
                      {quality.report.candidate}
                    </p>
                    <button
                      type="button"
                      className="mt-2 underline"
                      onClick={() => {
                        setCorrectionDraft(quality.report!.candidate);
                        document
                          .getElementById("manual-correction")
                          ?.closest("details")
                          ?.setAttribute("open", "");
                      }}
                    >
                      带入下方人工校订草稿
                    </button>
                    <p className="mt-2">只填入草稿；检查原图后，再由你保存。</p>
                  </details>
                )}
                <details className="text-sm">
                  <summary className="cursor-pointer text-primary">
                    人工校订历史原文
                  </summary>
                  <label
                    className="field-label mt-3"
                    htmlFor="manual-correction"
                  >
                    保留原始历史拼写，只校订有依据的错误。
                  </label>
                  <textarea
                    id="manual-correction"
                    className="field-control min-h-[160px] w-full leading-6"
                    value={correctionDraft}
                    onChange={(e) => setCorrectionDraft(e.target.value)}
                  />
                  <p className="my-2 text-xs leading-6 text-muted-foreground">
                    保存新版本后，旧证据仍可追溯；相关知识需重新验证。
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    disabled={
                      busy ||
                      !correctionDraft.trim() ||
                      correctionDraft === block.ocr_text_corrected
                    }
                    onClick={() =>
                      action(async () => {
                        const updated = await request<Block>(
                          `/workbench/blocks/${block.id}/correction`,
                          {
                            method: "POST",
                            body: JSON.stringify({
                              expected_raw_text: block.ocr_text_raw || "",
                              expected_corrected_text:
                                block.ocr_text_corrected ?? null,
                              corrected_text: correctionDraft,
                            }),
                          },
                        );
                        onBlockUpdated(updated);
                        setTextField("ocr_text_corrected");
                        setEvidence(null);
                        setMessage(
                          "校订版本已保存，请核对新文本并重新建立需要的证据。",
                        );
                      })
                    }
                  >
                    保存校订版本
                  </Button>
                </details>
                <p className="text-xs leading-6 text-muted-foreground">
                  在下方选取引句。默认使用整个区块；字符位置按原文版本保存。
                </p>
                <textarea
                  aria-label="选择证据引句"
                  readOnly
                  value={text}
                  className="field-control min-h-[160px] w-full leading-6"
                  onSelect={(e) => {
                    const input = e.currentTarget;
                    setRange([
                      Array.from(text.slice(0, input.selectionStart)).length,
                      Array.from(text.slice(0, input.selectionEnd)).length,
                    ]);
                    setEvidence(null);
                  }}
                />
                <p className="text-xs text-muted-foreground">
                  已选 {range[1] - range[0]} 个字符 · 区块级图像定位
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || !quote}
                    onClick={() =>
                      action(async () => {
                        await makeEvidence();
                        setMessage("证据已保存，可继续建立标注。");
                      })
                    }
                  >
                    保存证据
                  </Button>
                  {evidence && <EvidenceDialog evidence={[evidence]} />}
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || !text}
                    onClick={() =>
                      action(async () => {
                        await request(
                          `/workbench/blocks/${block.id}/text-review`,
                          {
                            method: "POST",
                            body: JSON.stringify({
                              text_field: textField,
                              expected_text: text,
                              approved: true,
                            }),
                          },
                        );
                        setMessage(
                          "当前文本版本已复核；请重建索引，使正式检索范围更新。",
                        );
                      })
                    }
                  >
                    确认当前文本
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">先选择一个区块。</p>
            )}
          </>
        )}
        {tab === "annotate" && (
          <>
            <form
              className="space-y-3 border-t pt-4"
              onSubmit={(e) => {
                e.preventDefault();
                if (fromAnnotation && !checkedCurrent) return;
                action(async () => {
                  const ev = evidence || (await makeEvidence());
                  const a = await workbenchApi.createAnnotation({
                    document_id: documentId,
                    source_unit_id: unitId ? Number(unitId) : null,
                    evidence_ids: [ev.id],
                    fields,
                  });
                  setFields({});
                  setMessage(
                    `标注 ${a.public_id.slice(0, 8)} 已进入审核队列。`,
                  );
                });
              }}
            >
              <h3 className="text-sm font-semibold">从引句建立研究标注</h3>
              <label>
                <span className="field-label">所属文书（可选）</span>
                <select
                  className="field-control w-full"
                  value={unitId}
                  onChange={(e) => setUnitId(e.target.value)}
                >
                  <option value="">未分段／暂不关联</option>
                  {units.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.title}
                    </option>
                  ))}
                </select>
              </label>
              {["name_form", "person", "event", "role"].map((key) => (
                <label key={key} className="block">
                  <span className="field-label">{FIELD_LABELS[key]}</span>
                  <Input
                    value={fields[key] || ""}
                    onChange={(e) =>
                      setFields({ ...fields, [key]: e.target.value })
                    }
                    placeholder={
                      key === "name_form"
                        ? "必须与引句中的拼写一致"
                        : "原文未记载时留空"
                    }
                  />
                </label>
              ))}
              <details>
                <summary className="cursor-pointer text-xs text-primary">
                  补充日期、职务、机构等字段
                </summary>
                <div className="mt-3 space-y-3">
                  {Object.keys(FIELD_LABELS)
                    .filter(
                      (k) =>
                        !["name_form", "person", "event", "role"].includes(k),
                    )
                    .map((key) => (
                      <label key={key} className="block">
                        <span className="field-label">{FIELD_LABELS[key]}</span>
                        <Input
                          value={fields[key] || ""}
                          onChange={(e) =>
                            setFields({ ...fields, [key]: e.target.value })
                          }
                        />
                      </label>
                    ))}
                </div>
              </details>
              {fromAnnotation && (
                <label className="flex items-start gap-2 text-xs leading-6">
                  <input
                    type="checkbox"
                    className="mt-1.5 accent-primary"
                    checked={checkedCurrent}
                    onChange={(e) => setCheckedCurrent(e.target.checked)}
                  />
                  我已对照当前原文，核对引句与下方标注内容。
                </label>
              )}
              <Button
                size="sm"
                disabled={
                  busy ||
                  (Boolean(fromAnnotation) && !checkedCurrent) ||
                  !quote ||
                  !Object.values(fields).some((v) => v.trim())
                }
              >
                保存为待审标注
              </Button>
              <Link className="ml-3 text-xs text-primary" href="/reviews">
                打开审核 →
              </Link>
            </form>
            <form
              className="space-y-3 border-t pt-4"
              onSubmit={(e) => {
                e.preventDefault();
                action(async () =>
                  setRun(
                    await workbenchApi.extract(documentId, {
                      page_start: Number(pageStart) || page?.page_number || 1,
                      page_end: Number(pageEnd) || page?.page_number || 1,
                      force_new: forceNew,
                    }),
                  ),
                );
              }}
            >
              <h3 className="text-sm font-semibold">AI 辅助抽取</h3>
              <p className="text-xs leading-6 text-muted-foreground">
                模型只生成候选。逐字核对引句后进入人工审核；不会覆盖已批准内容。
              </p>
              <div className="grid grid-cols-2 gap-2">
                <label>
                  <span className="field-label">起始 PDF 页</span>
                  <Input
                    type="number"
                    min="1"
                    placeholder={String(page?.page_number || 1)}
                    value={pageStart}
                    onChange={(e) => setPageStart(e.target.value)}
                  />
                </label>
                <label>
                  <span className="field-label">结束 PDF 页</span>
                  <Input
                    type="number"
                    min="1"
                    placeholder={String(page?.page_number || 1)}
                    value={pageEnd}
                    onChange={(e) => setPageEnd(e.target.value)}
                  />
                </label>
              </div>
              <label className="flex gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={forceNew}
                  onChange={(e) => setForceNew(e.target.checked)}
                />
                主动建立新批次（相同输入默认复用）
              </label>
              <Button
                variant="outline"
                size="sm"
                disabled={
                  busy ||
                  !block ||
                  (run && ["pending", "running"].includes(run.status)) ||
                  false
                }
              >
                抽取选定页段
              </Button>
              {run && (
                <div
                  className="rounded border p-3 text-xs leading-6"
                  role="status"
                >
                  批次 #{run.id} ·{" "}
                  {{
                    pending: "等待执行",
                    running: "抽取中",
                    completed: "已完成",
                    failed: "失败",
                  }[run.status] || run.status}
                  {run.output_summary && (
                    <p>
                      新增 {run.output_summary.created} 条候选；拦截{" "}
                      {run.output_summary.rejected_candidates.length}{" "}
                      条无效输出。
                    </p>
                  )}
                  {run.error_message && (
                    <p className="text-red-700">{run.error_message}</p>
                  )}
                  {run.status === "failed" && (
                    <button
                      type="button"
                      className="text-primary underline"
                      onClick={() =>
                        action(async () =>
                          setRun(await workbenchApi.retryExtraction(run.id)),
                        )
                      }
                    >
                      重试该批次
                    </button>
                  )}
                </div>
              )}
            </form>
          </>
        )}
        {tab === "segment" && (
          <>
            <h3 className="text-sm font-semibold">组合跨块／跨页文书</h3>
            <Button
              variant="outline"
              size="sm"
              disabled={
                busy ||
                !quote ||
                textField === "translation_zh" ||
                textField === "modern_english"
              }
              onClick={() =>
                action(async () => {
                  const e = evidence || (await makeEvidence());
                  setParts((prev) =>
                    prev.some((p) => p.id === e.id) ? prev : [...prev, e],
                  );
                  setMessage("已加入文书范围，可以翻页继续选择。");
                })
              }
            >
              将引句加入当前文书
            </Button>
            <ol className="space-y-2">
              {parts.map((p, i) => (
                <li key={p.id} className="rounded border p-3 text-xs">
                  <div className="flex justify-between">
                    <span>
                      {i + 1}. PDF {p.page_number} · 区块 {p.block_id}
                    </span>
                    <button
                      onClick={() =>
                        setParts(parts.filter((e) => e.id !== p.id))
                      }
                      className="text-primary"
                    >
                      移除
                    </button>
                  </div>
                  <p className="mt-2 line-clamp-2">{p.excerpt}</p>
                </li>
              ))}
            </ol>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                action(async () => {
                  await request(
                    `/workbench/documents/${documentId}/source-units`,
                    {
                      method: "POST",
                      body: JSON.stringify({
                        title: unitTitle,
                        unit_type: unitType,
                        original_date_text: unitOriginalDate || null,
                        normalized_date_start: unitDate || null,
                        normalized_date_end: unitDate || null,
                        date_precision: unitDate ? "day" : "unknown",
                        spans: parts.map((p) => ({
                          block_id: p.block_id,
                          revision_id: p.revision_id,
                          char_start: p.char_start,
                          char_end: p.char_end,
                        })),
                      }),
                    },
                  );
                  setParts([]);
                  setUnitTitle("");
                  loadUnits();
                  setMessage("文书分段已保存，请核对范围后确认。");
                });
              }}
            >
              <label>
                <span className="field-label">文书标题</span>
                <Input
                  value={unitTitle}
                  onChange={(e) => setUnitTitle(e.target.value)}
                  required
                />
              </label>
              <label>
                <span className="field-label">文书类型</span>
                <select
                  className="field-control w-full"
                  value={unitType}
                  onChange={(e) => setUnitType(e.target.value)}
                >
                  {[
                    ["other", "其他"],
                    ["letter_incoming", "来函"],
                    ["letter_outgoing", "复函"],
                    ["diary_entry", "日记条目"],
                    ["meeting_minutes", "会议记录"],
                    ["report", "报告"],
                    ["attachment", "附件"],
                  ].map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="field-label">原文日期</span>
                <Input
                  value={unitOriginalDate}
                  onChange={(e) => setUnitOriginalDate(e.target.value)}
                />
              </label>
              <label>
                <span className="field-label">规范日期（无明确依据留空）</span>
                <Input
                  type="date"
                  value={unitDate}
                  onChange={(e) => setUnitDate(e.target.value)}
                />
              </label>
              <Button
                size="sm"
                disabled={busy || !parts.length || !unitTitle.trim()}
              >
                保存文书分段
              </Button>
            </form>
            <div className="space-y-3 border-t pt-4">
              {units.map((u) => (
                <div key={u.id} className="rounded border p-3 text-sm">
                  <p>{u.title}</p>
                  <p className="my-2 text-xs text-muted-foreground">
                    {u.spans.length} 个来源片段 ·{" "}
                    {u.segmentation_status === "approved" ? "已确认" : "待复核"}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      action(async () => {
                        await request(
                          `/workbench/source-units/${u.id}/review`,
                          {
                            method: "POST",
                            body: JSON.stringify({
                              approved: u.segmentation_status !== "approved",
                              expected_updated_at: u.updated_at,
                            }),
                          },
                        );
                        loadUnits();
                        setMessage("文书审核状态已更新，请重建索引。");
                      })
                    }
                  >
                    {u.segmentation_status === "approved"
                      ? "退回待核对"
                      : "确认分段"}
                  </Button>
                </div>
              ))}
            </div>
          </>
        )}
        {tab === "metadata" && (
          <>
            <section className="space-y-3 border-b pb-4">
              <h3 className="text-sm font-semibold">语料集合</h3>
              <select
                aria-label="档案所属集合"
                className="field-control w-full"
                value={corpusId}
                onChange={(e) => setCorpusId(e.target.value)}
              >
                <option value="">尚未选择</option>
                {corpora.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !corpusId}
                onClick={() =>
                  action(async () => {
                    await request(`/workbench/corpora/${corpusId}/documents`, {
                      method: "POST",
                      body: JSON.stringify({ document_id: documentId }),
                    });
                    setMessage("档案已加入选定集合。");
                  })
                }
              >
                将档案加入集合
              </Button>
              <Input
                aria-label="新集合名称"
                placeholder="新建研究语料集合"
                value={corpusName}
                onChange={(e) => setCorpusName(e.target.value)}
              />
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !corpusName.trim()}
                onClick={() =>
                  action(async () => {
                    const corpus = await request<{ id: number; name: string }>(
                      "/workbench/corpora",
                      {
                        method: "POST",
                        body: JSON.stringify({ name: corpusName.trim() }),
                      },
                    );
                    setCorpora((prev) => [...prev, corpus]);
                    setCorpusId(String(corpus.id));
                    setCorpusName("");
                    setMessage("集合已建立，可将当前档案加入集合。");
                  })
                }
              >
                新建集合
              </Button>
            </section>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                action(async () => {
                  const values = Object.fromEntries(
                    [
                      "repository",
                      "archival_reference",
                      "collection_name",
                      "coverage_date_start",
                      "coverage_date_end",
                      "notes",
                    ].map((k) => [k, meta[k] || null]),
                  );
                  await request(`/workbench/documents/${documentId}/metadata`, {
                    method: "PUT",
                    body: JSON.stringify(values),
                  });
                  setMessage("档案元数据已保存。");
                });
              }}
            >
              <h3 className="text-sm font-semibold">馆藏与覆盖范围</h3>
              {[
                ["repository", "馆藏机构"],
                ["archival_reference", "档号"],
                ["collection_name", "卷名"],
                ["coverage_date_start", "覆盖起始日期"],
                ["coverage_date_end", "覆盖结束日期"],
                ["notes", "备注"],
              ].map(([key, label]) => (
                <label key={key} className="block">
                  <span className="field-label">{label}</span>
                  <Input
                    type={key.startsWith("coverage_") ? "date" : "text"}
                    value={meta[key] || ""}
                    onChange={(e) =>
                      setMeta({ ...meta, [key]: e.target.value })
                    }
                  />
                </label>
              ))}
              <p className="text-xs text-muted-foreground">
                年份依据档案实际覆盖范围录入，不从文件名推定。
              </p>
              <Button size="sm" disabled={busy}>
                保存档案信息
              </Button>
            </form>
            {page && (
              <form
                className="space-y-3 border-t pt-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  action(async () => {
                    await request(`/workbench/pages/${page.id}/label`, {
                      method: "PUT",
                      body: JSON.stringify({
                        original_page_label: pageLabel || null,
                        folio_side: folioSide,
                      }),
                    });
                    setMessage("原档页码已保存。");
                  });
                }}
              >
                <h3 className="text-sm font-semibold">
                  当前页：PDF {page.page_number}
                </h3>
                <label>
                  <span className="field-label">原档页码／folio</span>
                  <Input
                    value={pageLabel}
                    onChange={(e) => setPageLabel(e.target.value)}
                  />
                </label>
                <label>
                  <span className="field-label">正反面</span>
                  <select
                    className="field-control w-full"
                    value={folioSide}
                    onChange={(e) => setFolioSide(e.target.value)}
                  >
                    <option value="">未记录</option>
                    <option value="recto">正面 recto</option>
                    <option value="verso">反面 verso</option>
                  </select>
                </label>
                <Button size="sm" disabled={busy}>
                  保存原档页码
                </Button>
              </form>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
