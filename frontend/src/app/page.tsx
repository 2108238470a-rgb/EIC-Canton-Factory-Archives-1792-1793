"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  BookOpen,
  Search,
  ClipboardCheck,
  Upload,
} from "lucide-react";
import { ProcessingStatus } from "@/components/workbench/ProcessingStatus";
import { workbenchApi } from "@/lib/workbench";
import { Button } from "@/components/ui/button";
import { getStatusText } from "@/lib/utils";
export default function Home() {
  const [data, setData] = useState<Awaited<
    ReturnType<typeof workbenchApi.overview>
  > | null>(null);
  const [error, setError] = useState("");
  function load() {
    setError("");
    workbenchApi
      .overview()
      .then(setData)
      .catch((e) => setError(e.message));
  }
  useEffect(load, []);
  return (
    <div className="app-shell py-8 md:py-12">
      <div className="workspace-hero relative mb-9 grid gap-8 border-b pb-10 lg:grid-cols-[1.4fr_1fr] lg:items-center">
        <div>
          <p className="eyebrow">CANTON ARCHIVES / 研究工作台</p>
          <h1 className="max-w-2xl text-3xl font-semibold leading-snug tracking-tight md:text-5xl md:leading-tight">
            从档案出发，
            <br />
            <span className="text-primary">让研究有据可循。</span>
          </h1>
          <p className="section-description mt-4 max-w-2xl">
            整理档案，核对原文，将人物、事件与研究问题连接成可追溯的知识。
          </p>
        </div>
        <div className="hero-aside p-7 md:p-8">
          <p className="eyebrow">开始一次研究</p>
          <h2 className="mb-2 text-lg font-medium">
            让下一条线索，成为可靠的证据。
          </h2>
          <p className="mb-5 text-sm leading-7 text-muted-foreground">
            导入新的史料，或进入档案库继续阅读。原图、译校与证据标注在同一处对照。
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/upload">
              <Button>
                <Upload className="mr-2 h-4 w-4" />
                导入档案
              </Button>
            </Link>
            <Link href="/documents">
              <Button variant="outline">
                继续阅读 <ArrowUpRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </div>
      {error && (
        <div className="error-message" role="alert">
          {error}
          <button onClick={load} className="ml-3 underline">
            重新连接
          </button>
        </div>
      )}
      <dl className="my-8 grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
        {[
          ["documents", "档案文档"],
          ["annotations", "研究标注"],
          ["pending", "待审核"],
          ["entities", "人物与实体"],
        ].map(([key, label]) => (
          <div key={key} className="bg-card p-5 md:px-7">
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="mt-3 text-3xl font-medium tabular-nums">
              {data
                ? data[
                    key as "documents" | "annotations" | "pending" | "entities"
                  ]
                : "—"}
            </dd>
          </div>
        ))}
      </dl>
      <div className="research-paths mb-10 grid md:grid-cols-3">
        {[
          {
            href: "/documents",
            title: "阅读与标注",
            text: "对照页图和校文，圈定证据，整理文书。",
            icon: BookOpen,
          },
          {
            href: "/research",
            title: "查找历史证据",
            text: "按档案范围检索，再围绕证据提问。",
            icon: Search,
          },
          {
            href: "/reviews",
            title: "复核候选知识",
            text: "核对 AI 候选，逐项确认人物与事件。",
            icon: ClipboardCheck,
          },
        ].map((i) => (
          <Link
            key={i.href}
            href={i.href}
            className="group research-path p-6 transition hover:bg-accent/30"
          >
            <div className="flex justify-between text-primary">
              <i.icon className="h-5 w-5" />
              <ArrowUpRight className="h-4 w-4" />
            </div>
            <h2 className="mt-5 font-semibold">{i.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {i.text}
            </p>
          </Link>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section className="panel">
          <div className="flex justify-between border-b p-5">
            <h2 className="font-semibold">近期档案</h2>
            <Link className="text-sm text-primary" href="/documents">
              全部档案 →
            </Link>
          </div>
          {data?.recent_documents.length ? (
            data.recent_documents.map((d) => (
              <Link
                key={d.id}
                href={`/viewer/${d.id}`}
                className="flex items-center justify-between gap-4 border-b p-5 last:border-0 hover:bg-muted/30"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {d.original_filename}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span>
                      {d.page_count} 页 · {getStatusText(d.status)}
                    </span>
                    <ProcessingStatus document={d} />
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 shrink-0" />
              </Link>
            ))
          ) : (
            <p className="empty-state">
              {data ? "还没有档案，导入后即可开始。" : "正在加载档案…"}
            </p>
          )}
        </section>
        <section className="panel">
          <h2 className="border-b p-5 font-semibold">处理与抽取任务</h2>
          {data?.extractions.map((r) => (
            <Link
              key={`e${r.id}`}
              href="/reviews"
              className="block border-b p-4 text-sm"
            >
              知识抽取 #{r.id}
              <span className="float-right text-muted-foreground">
                {{
                  pending: "等待执行",
                  running: "抽取中",
                  completed: "已完成",
                  failed: "失败",
                  cancelled: "已取消",
                }[r.status] || r.status}
              </span>
              {r.error_message && (
                <p className="mt-2 text-red-700">{r.error_message}</p>
              )}
            </Link>
          ))}
          {data?.tasks.map((t) => (
            <div key={t.id} className="border-b p-4 text-sm">
              {{
                ocr: "档案文字识别",
                polish: "文本译校",
                export: "研究导出",
                pdf_ocr: "PDF 文字识别",
                ocr_correction: "原文纠错",
                modern_english: "现代英文转写",
                translation_zh: "中文翻译",
              }[t.task_type] || "档案处理"}
              <span className="float-right text-muted-foreground">
                {getStatusText(t.status)} · {t.progress}%
              </span>
            </div>
          ))}
          {data && !data.tasks.length && !data.extractions.length && (
            <p className="empty-state">暂无处理任务</p>
          )}
        </section>
      </div>
    </div>
  );
}
