"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Annotation, FIELD_LABELS, STATE_LABELS } from "@/types/workbench";
import { request, workbenchApi } from "@/lib/workbench";
import { EvidenceContent } from "@/components/workbench/EvidenceDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
function ReviewWorkspace() {
  const params = useSearchParams();
  const requested = Number(params.get("annotation"));
  const [items, setItems] = useState<Annotation[]>([]);
  const [selected, setSelected] = useState<Annotation | null>(null);
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [linkIds, setLinkIds] = useState<Record<string, string>>({});
  const [linkCandidates, setLinkCandidates] = useState<
    Record<string, Array<{ id: number; canonical_name: string }>>
  >({});
  const [entityId, setEntityId] = useState("");
  const [candidates, setCandidates] = useState<
    Array<{ id: number; canonical_name: string }>
  >([]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    workbenchApi
      .annotations(
        new URLSearchParams({ status, page: String(page), page_size: "20" }),
      )
      .then((r) => {
        if (active) {
          setItems(r.items);
          setTotal(r.total);
        }
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [status, page]);
  useEffect(() => {
    if (requested)
      workbenchApi
        .annotation(requested)
        .then(setSelected)
        .catch((e) => setError(e.message));
  }, [requested]);
  useEffect(() => {
    let active = true;
    setValues(selected?.fields || {});
    setLinkIds(
      Object.fromEntries(
        Object.entries(selected?.entity_links || {}).map(([k, v]) => [
          k,
          String(v),
        ]),
      ),
    );
    setLinkCandidates({});
    for (const field of ["organization", "location"]) {
      if (selected?.fields[field])
        request<{ items: Array<{ id: number; canonical_name: string }> }>(
          `/workbench/entities?q=${encodeURIComponent(selected.fields[field])}&entity_type=${field === "organization" ? "organization" : "place"}`,
        )
          .then((r) => {
            if (active)
              setLinkCandidates((prev) => ({ ...prev, [field]: r.items }));
          })
          .catch(() => {});
    }
    setEntityId(selected?.entity_id ? String(selected.entity_id) : "");
    setCandidates([]);
    if (selected?.fields.person) {
      request<{ items: Array<{ id: number; canonical_name: string }> }>(
        `/workbench/entities?q=${encodeURIComponent(selected.fields.person)}&entity_type=person`,
      )
        .then((r) => setCandidates(r.items))
        .catch(() => {});
    }
    return () => {
      active = false;
    };
  }, [selected]);
  async function review(field: string, decision: string) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const updated = await workbenchApi.review(selected.id, {
        expected_version: selected.version,
        field,
        decision,
        value: values[field],
        reason,
        entity_id:
          field === "person" && entityId
            ? Number(entityId)
            : linkIds[field]
              ? Number(linkIds[field])
              : undefined,
      });
      setSelected(updated);
      setItems((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    } catch (e) {
      setError((e as Error).message);
      try {
        setSelected(await workbenchApi.annotation(selected.id));
      } catch {}
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app-shell py-8">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Human review</p>
          <h1 className="section-title">审核工作台</h1>
          <p className="section-description mt-2">
            对照原图与引句，逐项判断。人物身份与事件分别确认。
          </p>
          <p className="mt-3 text-xs text-muted-foreground">
            第一次使用：选一条标注 → 看原图和引句 →
            修改内容或点击通过。只有需要重新核对的记录会暂停通过。
          </p>
        </div>
        <Link className="text-sm text-primary" href="/knowledge">
          返回知识库 →
        </Link>
      </div>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      <div className="grid gap-5 xl:grid-cols-[17rem_minmax(0,1fr)_minmax(18rem,1fr)]">
        <aside className="panel self-start">
          <div className="border-b p-4">
            <label className="field-label" htmlFor="review-status">
              审核队列
            </label>
            <select
              id="review-status"
              className="field-control w-full"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              {["pending", "needs_validation", "approved", "rejected"].map(
                (s) => (
                  <option key={s} value={s}>
                    {STATE_LABELS[s]}
                  </option>
                ),
              )}
            </select>
          </div>
          <div className="max-h-[65vh] overflow-auto">
            {loading ? (
              <p className="empty-state">加载中…</p>
            ) : items.length ? (
              items.map((a) => (
                <button
                  key={a.id}
                  onClick={() => setSelected(a)}
                  className={`w-full border-b p-4 text-left text-sm ${selected?.id === a.id ? "bg-primary/10" : "hover:bg-muted"}`}
                >
                  <p className="font-medium">
                    {a.fields.name_form ||
                      a.fields.person ||
                      a.fields.event ||
                      "研究标注"}
                  </p>
                  <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                    {a.evidence[0]?.excerpt}
                  </p>
                  <p className="mt-2 text-xs text-primary">
                    {STATE_LABELS[a.status]} · {a.public_id.slice(0, 8)}
                  </p>
                </button>
              ))
            ) : (
              <p className="empty-state">队列中没有记录。</p>
            )}
          </div>
          <div className="flex justify-between p-3">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 1 || loading}
              onClick={() => setPage(page - 1)}
            >
              上一页
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page * 20 >= total || loading}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </Button>
          </div>
        </aside>
        {selected ? (
          <>
            <section className="panel xl:max-h-[85vh] xl:overflow-auto p-5">
              <h2 className="mb-5 font-semibold">原文证据</h2>
              <div className="space-y-8">
                {selected.evidence.map((e) => (
                  <EvidenceContent key={e.id} evidence={e} />
                ))}
              </div>
            </section>
            <section className="panel xl:max-h-[85vh] xl:overflow-auto p-5">
              <div className="mb-5 flex justify-between">
                <h2 className="font-semibold">字段复核</h2>
                <span className="text-xs text-muted-foreground">
                  版本 {selected.version}
                </span>
              </div>
              {selected.status === "needs_validation" && (
                <div className="review-guidance mb-5">
                  <p className="font-medium">这条标注引用的原文有更新</p>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">
                    标注仍保留原来的内容，但需要再核对一次来源，才能通过审核。
                  </p>
                  <ol className="my-4 space-y-2 text-xs leading-6">
                    <li>1. 打开当前原文，对照这里的旧引句。</li>
                    <li>2. 选取最新原文；原有标注内容会带入表单。</li>
                    <li>3. 保存新的标注，再回到审核页确认。</li>
                  </ol>
                  <Link
                    className="inline-flex rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
                    href={`/viewer/${selected.document_id}?page=${selected.evidence[0]?.page_number || 1}&block=${selected.evidence[0]?.block_id || ""}&from_annotation=${selected.id}`}
                  >
                    打开原文，重新核对 →
                  </Link>
                  <p className="mt-3 text-xs text-muted-foreground">
                    旧记录与审核历史会保留；不会自动覆盖已经确认的判断。
                  </p>
                </div>
              )}
              <label className="field-label" htmlFor="review-reason">
                本次判断依据／理由
              </label>
              <textarea
                id="review-reason"
                className="field-control mb-5 w-full"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="记录修改理由、歧义或反对证据"
              />
              {Object.keys(selected.fields).map((field) => (
                <div key={field} className="mb-5 border-b pb-5">
                  <label className="field-label" htmlFor={`field-${field}`}>
                    {FIELD_LABELS[field] || field}{" "}
                    <span className="ml-2 status-badge">
                      {STATE_LABELS[selected.field_states[field]] || "待审核"}
                    </span>
                  </label>
                  <textarea
                    id={`field-${field}`}
                    className="field-control w-full"
                    value={values[field] ?? ""}
                    onChange={(e) =>
                      setValues({ ...values, [field]: e.target.value })
                    }
                  />
                  {field === "person" && (
                    <div className="my-2">
                      <label
                        className="field-label"
                        htmlFor="candidate-identity"
                      >
                        人物身份（同名不会自动合并）
                      </label>
                      <select
                        id="candidate-identity"
                        className="field-control w-full"
                        value={entityId}
                        onChange={(e) => setEntityId(e.target.value)}
                      >
                        <option value="">批准时建立独立人物</option>
                        {selected.entity_id &&
                          !candidates.some(
                            (c) => c.id === selected.entity_id,
                          ) && (
                            <option value={selected.entity_id}>
                              当前人物 #{selected.entity_id}
                            </option>
                          )}
                        {candidates.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.canonical_name} #{c.id}
                          </option>
                        ))}
                      </select>
                      {selected.entity_id && (
                        <Button
                          disabled={busy}
                          size="sm"
                          variant="outline"
                          className="mt-2"
                          onClick={() => {
                            setEntityId("");
                            review(field, "pending");
                          }}
                        >
                          撤销当前身份链接
                        </Button>
                      )}
                    </div>
                  )}
                  {["organization", "location"].includes(field) && (
                    <label className="my-2 block">
                      <span className="field-label">
                        规范{field === "organization" ? "机构" : "地点"}
                      </span>
                      <select
                        className="field-control w-full"
                        value={linkIds[field] || ""}
                        onChange={(e) =>
                          setLinkIds({ ...linkIds, [field]: e.target.value })
                        }
                      >
                        <option value="">批准时建立独立记录</option>
                        {selected.entity_links?.[field] &&
                          !(linkCandidates[field] || []).some(
                            (c) => c.id === selected.entity_links?.[field],
                          ) && (
                            <option value={selected.entity_links[field]}>
                              当前记录 #{selected.entity_links[field]}
                            </option>
                          )}
                        {(linkCandidates[field] || []).map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.canonical_name} #{c.id}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      disabled={busy || selected.status === "needs_validation"}
                      onClick={() => review(field, "approved")}
                    >
                      通过
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => review(field, "rejected")}
                    >
                      驳回
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => review(field, "pending")}
                    >
                      保存为待审
                    </Button>
                  </div>
                </div>
              ))}
              <details>
                <summary className="cursor-pointer text-sm">
                  修改与审核历史 ({selected.history.length})
                </summary>
                <ol className="mt-3 space-y-3 text-xs text-muted-foreground">
                  {selected.history.map((h) => (
                    <li key={h.id}>
                      {FIELD_LABELS[h.field]} · {STATE_LABELS[h.decision]} ·{" "}
                      {h.reviewer}
                      <p>{h.reason || "未填写理由"}</p>
                      <time>{h.created_at}</time>
                    </li>
                  ))}
                </ol>
              </details>
            </section>
          </>
        ) : (
          <div className="panel empty-state xl:col-span-2">
            选择一条候选标注，开始对照证据审核。
          </div>
        )}
      </div>
    </div>
  );
}
export default function ReviewPage() {
  return (
    <Suspense fallback={<p className="empty-state">加载审核工作台…</p>}>
      <ReviewWorkspace />
    </Suspense>
  );
}
