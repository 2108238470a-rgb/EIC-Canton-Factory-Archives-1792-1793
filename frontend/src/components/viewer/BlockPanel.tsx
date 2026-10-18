"use client";

import { Block, Task } from "@/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Loader2, Sparkles, ScanText, FileText, BookText } from "lucide-react";

interface BlockPanelProps {
  block: Block | null;
  pageMarkdown?: string;
  onPagePolish?: () => void;
  onDocumentPolish?: () => void;
  isPolishing?: boolean;
  activeTask?: Task | null;
}

export function BlockPanel({
  block,
  pageMarkdown,
  onPagePolish,
  onDocumentPolish,
  isPolishing,
  activeTask,
}: BlockPanelProps) {
  const activeScope = activeTask?.result?.scope;
  const taskLabel = getTaskLabel(activeTask);

  if (!block) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-sm rounded-lg border border-slate-200 bg-white/80 p-8 text-center shadow-none">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="h-7 w-7" />
          </div>
          <h3 className="text-lg font-semibold text-slate-900">
            选择一个区块开始阅读
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            点击左侧页面中的识别框，查看 OCR 原文和纠错结果。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 h-full flex-col bg-white/70">
      <div className="border-b border-slate-200 px-4 py-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
              <ScanText className="h-3.5 w-3.5" />
              区块 {block.block_index + 1}
            </div>
            <h3 className="text-lg font-semibold text-slate-900">
              {block.block_label || "text"}
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              {block.confidence
                ? `置信度 ${(block.confidence * 100).toFixed(1)}%`
                : "暂无置信度信息"}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {onPagePolish && (
            <Button
              size="sm"
              variant="outline"
              className="rounded-full"
              onClick={() => onPagePolish()}
              disabled={isPolishing}
            >
              {isPolishing && activeScope === "page" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <FileText className="mr-2 h-4 w-4" />
              )}
              纠错本页
            </Button>
          )}
          {onDocumentPolish && (
            <Button
              size="sm"
              className="rounded-full shadow-none"
              onClick={() => onDocumentPolish()}
              disabled={isPolishing}
            >
              {isPolishing && activeScope === "document" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <BookText className="mr-2 h-4 w-4" />
              )}
              纠错全文
            </Button>
          )}
        </div>

        {activeTask && (
          <div className="mt-4 rounded-md border border-primary/15 bg-primary/5 px-4 py-3 text-sm text-slate-600">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium text-slate-900">{taskLabel}</span>
              <span>{activeTask.progress}%</span>
            </div>
          </div>
        )}
      </div>

      <Tabs
        defaultValue="raw"
        className="flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        <TabsList className="mx-5 mt-5 grid grid-cols-3 rounded-md bg-slate-100 p-1">
          <TabsTrigger value="raw" className="rounded-xl">
            原文
          </TabsTrigger>
          <TabsTrigger value="corrected" className="rounded-xl">
            纠错
          </TabsTrigger>
          <TabsTrigger value="page" className="rounded-xl">
            页级 OCR
          </TabsTrigger>
        </TabsList>

        <div className="min-h-0 flex-1 overflow-auto overscroll-contain px-4 py-3">
          <TabsContent value="raw" className="mt-0">
            <TextContent
              icon={<ScanText className="h-4 w-4" />}
              title="OCR 原文"
              text={block.ocr_text_raw}
              placeholder="暂无 OCR 文本"
            />
          </TabsContent>

          <TabsContent value="corrected" className="mt-0">
            <TextContent
              icon={<Sparkles className="h-4 w-4" />}
              title="OCR 纠错版"
              text={block.ocr_text_corrected}
              placeholder="暂无纠错文本，请点击「纠错本页」或「纠错全文」按钮"
            />
          </TabsContent>

          <TabsContent value="page" className="mt-0">
            <TextContent
              icon={<FileText className="h-4 w-4" />}
              title="当前页 OCR Markdown"
              text={pageMarkdown}
              placeholder="暂无当前页 OCR Markdown"
            />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

function getTaskLabel(task: Task | null | undefined): string {
  if (!task) return "";

  const result = task.result;
  const scope = result?.scope;
  const processed =
    typeof result?.processed === "number" ? result.processed : null;
  const skipped = typeof result?.skipped === "number" ? result.skipped : null;
  const total = typeof result?.total === "number" ? result.total : null;
  const processedPages =
    typeof result?.processed_pages === "number" ? result.processed_pages : null;
  const skippedPages =
    typeof result?.skipped_pages === "number" ? result.skipped_pages : null;
  const pageNumber =
    typeof result?.page_number === "number" ? result.page_number : null;
  const pageCount =
    typeof result?.page_count === "number" ? result.page_count : null;
  const failedPageNumber =
    typeof result?.failed_page_number === "number"
      ? result.failed_page_number
      : null;
  const totalTokens =
    typeof result?.token_usage?.total_tokens === "number"
      ? result.token_usage.total_tokens
      : null;
  const llmCalls =
    typeof result?.llm_calls === "number"
      ? result.llm_calls
      : typeof result?.token_usage?.calls === "number"
        ? result.token_usage.calls
        : null;

  if (task.status === "completed") {
    const blockSummary =
      processed !== null || skipped !== null
        ? `处理 ${processed ?? 0} 个区块，跳过 ${skipped ?? 0} 个区块`
        : "";
    const usageSummary = [
      totalTokens !== null ? `${totalTokens.toLocaleString()} tokens` : "",
      llmCalls !== null ? `${llmCalls} 次调用` : "",
    ]
      .filter(Boolean)
      .join("，");
    const summary = [blockSummary, usageSummary].filter(Boolean).join("；");
    return summary ? `纠错完成：${summary}` : "纠错完成";
  }

  if (task.status === "failed") {
    return failedPageNumber !== null
      ? `纠错失败：第 ${failedPageNumber} 页处理失败`
      : "纠错任务失败";
  }

  if (scope === "page") {
    if (processed !== null || skipped !== null || total !== null) {
      return `正在批量纠错本页 ${processed ?? 0} / ${total ?? 0} 个区块，跳过 ${skipped ?? 0} 个`;
    }
    return pageNumber !== null
      ? `正在批量纠错第 ${pageNumber} 页`
      : "正在批量纠错当前页";
  }

  if (scope === "document") {
    if (processedPages !== null || skippedPages !== null) {
      const completedPages = (processedPages ?? 0) + (skippedPages ?? 0);
      const pageProgress =
        pageCount !== null
          ? `${completedPages} / ${pageCount}`
          : `${completedPages}`;
      return `正在批量纠错全文，已完成 ${pageProgress} 页（跳过 ${skippedPages ?? 0} 页）`;
    }
    return pageNumber !== null && pageCount !== null
      ? `正在批量纠错全文，第 ${pageNumber} / ${pageCount} 页`
      : "正在批量纠错全文";
  }

  return "正在处理纠错任务";
}

function TextContent({
  icon,
  title,
  text,
  placeholder,
}: {
  icon: React.ReactNode;
  title: string;
  text: string | null | undefined;
  placeholder: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
        {icon}
        {title}
      </div>
      {text ? (
        <div className="prose prose-sm max-w-none text-slate-700">
          <p className="whitespace-pre-wrap leading-7">{text}</p>
        </div>
      ) : (
        <p className="text-sm italic text-slate-400">{placeholder}</p>
      )}
    </div>
  );
}
