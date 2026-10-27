"use client";

import { knowledgeApi } from "@/lib/api";
import { ListShell } from "./ListShell";
import { usePagedList } from "./usePagedList";
import { CERTAINTY_LABELS, PREDICATE_LABELS, label } from "./labels";

const fetchAssertions = (page: number, pageSize: number) =>
  knowledgeApi.listAssertions(page, pageSize);

export function AssertionList() {
  const list = usePagedList(fetchAssertions);

  return (
    <ListShell {...list} onPageChange={list.setPage} emptyText="还没有断言。">
      {list.items.map((assertion) => (
        <div key={assertion.id} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm">
          <p className="text-slate-800">
            实体 #{assertion.subject_entity_id}{" "}
            <span className="font-medium text-primary">{label(PREDICATE_LABELS, assertion.predicate)}</span>{" "}
            {assertion.object_entity_id ? `实体 #${assertion.object_entity_id}` : assertion.object_literal || "-"}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {label(CERTAINTY_LABELS, assertion.certainty)} · 证据 {assertion.evidence_links.length} 条
            {assertion.is_inferred ? " · 推断" : ""}
          </p>
        </div>
      ))}
    </ListShell>
  );
}
