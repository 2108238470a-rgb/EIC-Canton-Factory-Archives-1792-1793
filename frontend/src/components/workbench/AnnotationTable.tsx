"use client";
import Link from "next/link";
import { Annotation, STATE_LABELS } from "@/types/workbench";
import { EvidenceDialog } from "./EvidenceDialog";
const COLUMNS = [
  ["public_id", "标注序号"],
  ["archival_year", "档案年份"],
  ["page", "档案页码"],
  ["document_date", "文书日期"],
  ["person", "人名"],
  ["name_form", "人名形式"],
  ["honorific", "敬称或称号"],
  ["nationality", "国籍"],
  ["occupation", "职业"],
  ["organization", "人物所属机构"],
  ["event", "事件"],
  ["location", "地点"],
  ["related_event", "相关事件"],
  ["evidence", "证据位置（可贴图）"],
  ["review", "需要复核"],
  ["notes", "备注"],
];
export function AnnotationTable({ items }: { items: Annotation[] }) {
  if (!items.length)
    return (
      <div className="empty-state">
        当前范围没有标注。打开档案阅读器，选择原文建立标注，或发起 AI 候选抽取。
      </div>
    );
  return (
    <div className="overflow-auto">
      <table className="research-table min-w-[1900px]">
        <caption className="sr-only">
          人物提及与事件角色的 16 列标注总表
        </caption>
        <thead>
          <tr>
            {COLUMNS.map(([key, title]) => (
              <th key={key}>{title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id}>
              {COLUMNS.map(([key]) => (
                <td key={key}>
                  {key === "public_id" ? (
                    <Link
                      href={`/reviews?annotation=${a.id}`}
                      className="text-primary underline underline-offset-4"
                      title={a.public_id}
                    >
                      {a.public_id.slice(0, 8)}
                    </Link>
                  ) : key === "archival_year" ? (
                    a.archival_year || "—"
                  ) : key === "page" ? (
                    a.evidence
                      .map(
                        (e) =>
                          `PDF ${e.page_number} / ${e.original_page_label || "原档未录入"}`,
                      )
                      .join("；")
                  ) : key === "evidence" ? (
                    <EvidenceDialog evidence={a.evidence} />
                  ) : key === "review" ? (
                    <Link
                      href={`/reviews?annotation=${a.id}`}
                      className="status-badge"
                    >
                      {STATE_LABELS[a.status] || a.status}
                    </Link>
                  ) : key === "person" && a.entity_id ? (
                    <Link
                      href={`/knowledge/dossiers/${a.entity_id}`}
                      className="text-primary"
                    >
                      {a.fields.person}
                    </Link>
                  ) : key === "event" && a.event_id ? (
                    <Link
                      href={`/knowledge/events/${a.event_id}`}
                      className="text-primary"
                    >
                      {a.fields.event}
                    </Link>
                  ) : (
                    <span className="whitespace-pre-wrap">
                      {a.fields[key] || "—"}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
