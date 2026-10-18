"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { knowledgeApi } from "@/lib/api";
import { EntityType } from "@/types/knowledge";
import { ListShell } from "./ListShell";
import { usePagedList } from "./usePagedList";
import { DISAMBIGUATION_LABELS, ENTITY_TYPE_LABELS, label } from "./labels";

export function EntityList({ onChanged }: { onChanged: () => void }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const list = usePagedList(knowledgeApi.listEntities, search);

  const [name, setName] = useState("");
  const [entityType, setEntityType] = useState<EntityType>("person");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      await knowledgeApi.createEntity({ entity_type: entityType, canonical_name: name.trim() });
      setName("");
      await list.reload();
      onChanged();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setSearch(query.trim());
          }}
        >
          <label htmlFor="entity-search" className="sr-only">搜索实体</label>
          <Input
            id="entity-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="按名称搜索"
            className="w-64"
          />
          <Button type="submit" variant="outline">搜索</Button>
        </form>

        <form className="flex flex-wrap items-center gap-2" onSubmit={handleCreate}>
          <label htmlFor="entity-type" className="sr-only">实体类型</label>
          <select
            id="entity-type"
            value={entityType}
            onChange={(event) => setEntityType(event.target.value as EntityType)}
            className="h-10 rounded-md border border-input bg-white px-3 text-sm"
          >
            {Object.entries(ENTITY_TYPE_LABELS).map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
          <label htmlFor="entity-name" className="sr-only">规范名称</label>
          <Input
            id="entity-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="规范名称，如 Henry Browne"
            className="w-64"
          />
          <Button type="submit" disabled={saving || !name.trim()}>新建实体</Button>
        </form>
      </div>
      {formError && <p role="alert" className="text-sm text-red-700">{formError}</p>}

      <ListShell {...list} onPageChange={list.setPage} emptyText="还没有实体。可以在右上角手动新建，后续由抽取流程自动生成候选。">
        {list.items.map((entity) => (
          <Link
            key={entity.id}
            href={`/knowledge/entities/${entity.id}`}
            className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3 transition hover:border-primary/50"
          >
            <div>
              <p className="font-medium text-slate-900">{entity.canonical_name}</p>
              <p className="text-xs text-slate-500">
                {label(ENTITY_TYPE_LABELS, entity.entity_type)} · 别名 {entity.names.length} 个
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
              {label(DISAMBIGUATION_LABELS, entity.disambiguation_status)}
            </span>
          </Link>
        ))}
      </ListShell>
    </div>
  );
}
