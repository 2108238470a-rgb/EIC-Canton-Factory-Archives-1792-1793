"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { knowledgeApi } from "@/lib/api";
import { ListShell } from "./ListShell";
import { usePagedList } from "./usePagedList";
import { EVENT_TYPE_LABELS, label } from "./labels";

export function EventList() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const list = usePagedList(knowledgeApi.listEvents, search);

  return (
    <div className="space-y-5">
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(query.trim());
        }}
      >
        <label htmlFor="event-search" className="sr-only">搜索事件</label>
        <Input
          id="event-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="按标题搜索"
          className="w-64"
        />
        <Button type="submit" variant="outline">搜索</Button>
      </form>

      <ListShell {...list} onPageChange={list.setPage} emptyText="还没有事件。">
        {list.items.map((event) => (
          <div key={event.id} className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <p className="font-medium text-slate-900">{event.title}</p>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">
                {label(EVENT_TYPE_LABELS, event.event_type)}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {event.start_date || "日期未知"}
              {event.end_date ? ` – ${event.end_date}` : ""} · 参与者 {event.participants.length} 个
            </p>
            {event.summary && <p className="mt-2 text-sm text-slate-600">{event.summary}</p>}
          </div>
        ))}
      </ListShell>
    </div>
  );
}
