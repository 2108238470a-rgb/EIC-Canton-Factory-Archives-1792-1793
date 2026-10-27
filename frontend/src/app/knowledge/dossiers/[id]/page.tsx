"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { request } from "@/lib/workbench";
import {
  Annotation,
  Evidence,
  FIELD_LABELS,
  STATE_LABELS,
} from "@/types/workbench";
import { EvidenceDialog } from "@/components/workbench/EvidenceDialog";
import { AnnotationTable } from "@/components/workbench/AnnotationTable";
interface Dossier {
  id: number;
  canonical_name: string;
  entity_type: string;
  notes?: string;
  names: string[];
  annotations: Annotation[];
  assertions: Array<{
    id: number;
    predicate: string;
    object_literal?: string;
    object_name?: string;
    status: string;
    evidence: Evidence[];
  }>;
  events: Array<{ id: number; title: string }>;
  identity_decisions: Array<{
    id: number;
    status: string;
    basis: string;
    reviewer: string;
  }>;
  legacy_roles: Array<{
    id: number;
    role_title: string;
    start_date?: string;
    end_date?: string;
  }>;
}
export default function EntityPage() {
  const { id } = useParams();
  const [data, setData] = useState<Dossier | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    request<Dossier>(`/workbench/entities/${id}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);
  return (
    <div className="app-shell py-8">
      <Link className="text-sm text-primary" href="/knowledge">
        ← 知识库
      </Link>
      {error ? (
        <p role="alert" className="error-message">
          {error}
        </p>
      ) : !data ? (
        <p className="empty-state">正在加载人物档案…</p>
      ) : (
        <>
          <header className="my-7 border-b pb-7">
            <p className="eyebrow">Entity dossier · #{data.id}</p>
            <h1 className="section-title">{data.canonical_name}</h1>
            <p className="mt-3 text-sm text-muted-foreground">
              原文形式：
              {Array.from(
                new Set([
                  ...data.names,
                  ...data.annotations
                    .map((a) => a.fields.name_form)
                    .filter(Boolean),
                ]),
              ).join("；") || "暂无"}
            </p>
            {data.notes && <p className="mt-3 text-sm">{data.notes}</p>}
          </header>
          <h2 className="mb-4 font-semibold">原文提及与事件角色</h2>
          <div className="panel">
            <AnnotationTable items={data.annotations} />
          </div>
          <section className="panel mt-6 p-5">
            <h2 className="mb-4 font-semibold">任职与研究判断</h2>
            {data.assertions.length ? (
              data.assertions.map((a) => (
                <article key={a.id} className="border-b py-4 last:border-0">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-medium">
                      {FIELD_LABELS[a.predicate] ||
                        (
                          {
                            held_role: "历史任职",
                            appointed_to_role: "任命",
                            represented_org: "机构归属",
                            event_participation: "事件参与",
                          } as Record<string, string>
                        )[a.predicate] ||
                        "研究判断"}
                    </h3>
                    <span className="status-badge">
                      {STATE_LABELS[a.status] || a.status}
                    </span>
                  </div>
                  <p className="my-3 text-sm">
                    {a.object_literal || a.object_name || "详见原文"}
                  </p>
                  <EvidenceDialog evidence={a.evidence} />
                </article>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                暂无有来源的任职与研究判断。
              </p>
            )}
          </section>
          <div className="mt-7 grid gap-5 md:grid-cols-2">
            <section className="panel p-5">
              <h2 className="mb-4 font-semibold">参与事件</h2>
              {data.events.length ? (
                data.events.map((e) => (
                  <Link
                    key={e.id}
                    className="block border-b py-3 text-sm text-primary"
                    href={`/knowledge/events/${e.id}`}
                  >
                    {e.title} →
                  </Link>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  暂无已关联事件。
                </p>
              )}
            </section>
            <section className="panel p-5">
              <h2 className="mb-4 font-semibold">身份判断历史</h2>
              {data.identity_decisions.length ? (
                data.identity_decisions.map((d) => (
                  <div key={d.id} className="border-b py-3 text-sm">
                    <span className="status-badge">
                      {STATE_LABELS[d.status] || d.status}
                    </span>
                    <p className="mt-2">
                      {d.basis || "未填写理由"} · {d.reviewer || "历史记录"}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">暂无身份判断。</p>
              )}
              {data.legacy_roles.map((r) => (
                <p key={r.id} className="notice mt-3">
                  历史任职记录：{r.role_title} · {r.start_date || "日期未知"}—
                  {r.end_date || "日期未知"}（保留原记录，待核验证据）
                </p>
              ))}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
