"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { request } from "@/lib/workbench";
import { Annotation, STATE_LABELS } from "@/types/workbench";
import { AnnotationTable } from "@/components/workbench/AnnotationTable";
interface Event {
  id: number;
  title: string;
  summary?: string;
  date_start?: string;
  date_end?: string;
  date_precision?: string;
  status: string;
  annotations: Annotation[];
  participants: Array<{
    id: number;
    entity_id: number;
    entity_name: string;
    role: string;
  }>;
  mentions: Array<{ id: number; summary: string }>;
  relations: Array<{
    id: number;
    target_event_id: number;
    relation_type: string;
  }>;
}
export default function EventPage() {
  const { id } = useParams();
  const [data, setData] = useState<Event | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    request<Event>(`/workbench/events/${id}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);
  return (
    <div className="app-shell py-8">
      <Link className="text-sm text-primary" href="/knowledge">
        ← 知识库
      </Link>
      {error ? (
        <p className="error-message" role="alert">
          {error}
        </p>
      ) : !data ? (
        <p className="empty-state">正在加载事件…</p>
      ) : (
        <>
          <header className="my-7 border-b pb-7">
            <p className="eyebrow">Historical event · #{data.id}</p>
            <h1 className="section-title">{data.title}</h1>
            <p className="mt-3 text-sm text-muted-foreground">
              {data.date_start || "日期未确定"}{" "}
              {data.date_end ? `— ${data.date_end}` : ""} ·{" "}
              {data.date_precision || "精度未知"} ·{" "}
              {STATE_LABELS[data.status] || data.status}
            </p>
            {data.summary && (
              <p className="mt-4 text-sm leading-7">{data.summary}</p>
            )}
          </header>
          <section className="panel mb-6 p-5">
            <h2 className="mb-3 font-semibold">参与者与角色</h2>
            {data.participants.length ? (
              data.participants.map((p) => (
                <Link
                  key={p.id}
                  href={`/knowledge/dossiers/${p.entity_id}`}
                  className="mr-4 inline-block py-2 text-sm text-primary"
                >
                  {p.entity_name} · {p.role}
                </Link>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                暂无已复核参与关系。
              </p>
            )}
          </section>
          <h2 className="mb-4 font-semibold">文书记载与证据</h2>
          <div className="panel">
            <AnnotationTable items={data.annotations} />
          </div>
          {data.mentions.map((m) => (
            <p key={m.id} className="panel mt-3 p-4 text-sm">
              {m.summary}
            </p>
          ))}
          {data.relations.length > 0 && (
            <section className="panel mt-5 p-5">
              <h2 className="font-semibold">相关事件</h2>
              {data.relations.map((r) => (
                <Link
                  key={r.id}
                  className="mt-3 block text-sm text-primary"
                  href={`/knowledge/events/${r.target_event_id}`}
                >
                  {r.relation_type} → #{r.target_event_id}
                </Link>
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}
