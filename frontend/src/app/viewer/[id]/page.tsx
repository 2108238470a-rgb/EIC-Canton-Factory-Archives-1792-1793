"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { documentApi, pageApi, blockApi, taskApi } from "@/lib/api";
import { Document, Page, Block, Task } from "@/types";
import { PageViewer } from "@/components/viewer/PageViewer";
import { BlockPanel } from "@/components/viewer/BlockPanel";
import { PageNavigator } from "@/components/viewer/PageNavigator";
import { ArrowLeft, Loader2, LayoutPanelLeft, ScanText, BookText, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

export default function ViewerPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const documentId = Number(params.id);
  const initialPage = Number(searchParams.get("page")) || 1;

  const [document, setDocument] = useState<Document | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [currentPageNumber, setCurrentPageNumber] = useState(initialPage);
  const [currentPage, setCurrentPage] = useState<Page | null>(null);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [selectedBlock, setSelectedBlock] = useState<Block | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPolishing, setIsPolishing] = useState(false);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [showBlockList, setShowBlockList] = useState(true);
  const [readingMode, setReadingMode] = useState<"page" | "document">("page");

  const fetchDocumentData = useCallback(async () => {
    const doc = await documentApi.get(documentId);
    setDocument(doc);

    const pagesResponse = await documentApi.getPages(documentId);
    setPages(pagesResponse.items);
    return { doc, pages: pagesResponse.items };
  }, [documentId]);

  const fetchCurrentPageData = useCallback(async (pageNumber: number, availablePages?: Page[]) => {
    const pageList = availablePages || pages;
    if (pageList.length === 0) return null;

    const page = pageList.find((item) => item.page_number === pageNumber) || pageList[0];
    if (!page) return null;

    const pageDetail = await pageApi.get(page.id);
    const blocksResponse = await pageApi.getBlocks(page.id);
    const nextBlocks = blocksResponse.items;

    setCurrentPage(pageDetail);
    setBlocks(nextBlocks);
    setSelectedBlock((prev) => nextBlocks.find((item) => item.id === prev?.id) || nextBlocks[0] || null);
    return { page: pageDetail, blocks: nextBlocks };
  }, [pages]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        await fetchDocumentData();
      } catch (error) {
        console.error("Failed to fetch document:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [fetchDocumentData]);

  useEffect(() => {
    const fetchPageData = async () => {
      if (pages.length === 0) return;

      try {
        await fetchCurrentPageData(currentPageNumber, pages);
      } catch (error) {
        console.error("Failed to fetch page:", error);
      }
    };

    fetchPageData();
  }, [pages, currentPageNumber, fetchCurrentPageData]);

  const handleBlockSelect = useCallback((block: Block) => {
    setSelectedBlock(block);
    setReadingMode("page");
  }, []);

  const handlePageChange = useCallback((page: number) => {
    setCurrentPageNumber(page);
    setReadingMode("page");
  }, []);

  const runPolishTask = useCallback(async (taskPromise: Promise<Task>, refreshScope: "block" | "page" | "document", blockId?: number) => {
    setIsPolishing(true);
    try {
      const task = await taskPromise;
      setActiveTask(task);
      await taskApi.poll(task.id, (updatedTask) => {
        setActiveTask(updatedTask);
      });

      if (refreshScope === "block" && blockId) {
        const updatedBlock = await blockApi.get(blockId);
        setBlocks((prev) => prev.map((item) => (item.id === blockId ? updatedBlock : item)));
        setSelectedBlock(updatedBlock);
      } else if (refreshScope === "page") {
        await fetchCurrentPageData(currentPageNumber);
      } else {
        const { pages: refreshedPages } = await fetchDocumentData();
        await fetchCurrentPageData(currentPageNumber, refreshedPages);
      }
    } catch (error) {
      console.error("Polish failed:", error);
    } finally {
      setIsPolishing(false);
    }
  }, [currentPageNumber, fetchCurrentPageData, fetchDocumentData]);

  const handlePagePolish = useCallback(async () => {
    if (!currentPage) return;
    await runPolishTask(pageApi.runPolish(currentPage.id, { modes: ["ocr_correction"] }), "page");
  }, [currentPage, runPolishTask]);

  const handleDocumentPolish = useCallback(async () => {
    await runPolishTask(documentApi.runPolish(documentId, { modes: ["ocr_correction"] }), "document");
  }, [documentId, runPolishTask]);

  const orderedBlockTexts = useMemo(() => {
    return blocks
      .slice()
      .sort((a, b) => {
        const ay = a.bbox?.[1] ?? 0;
        const by = b.bbox?.[1] ?? 0;
        if (ay !== by) return ay - by;
        const ax = a.bbox?.[0] ?? 0;
        const bx = b.bbox?.[0] ?? 0;
        return ax - bx;
      })
      .map((block) => ({
        id: block.id,
        label: block.block_label || "text",
        index: block.block_index + 1,
        text:
          block.ocr_text_corrected ||
          block.ocr_text_raw ||
          "",
      }))
      .filter((block) => block.text);
  }, [blocks]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!document || pages.length === 0) {
    return (
      <div className="flex h-screen flex-col items-center justify-center">
        <p className="mb-4 text-muted-foreground">文档不存在或暂无页面</p>
        <Link href="/documents">
          <Button>返回列表</Button>
        </Link>
      </div>
    );
  }

  const currentPageMarkdown = currentPage?.markdown_content || "";
  const fullMarkdown = document.full_markdown || pages.map((page) => page.markdown_content || "").filter(Boolean).join("\n\n");

  return (
    <div className="app-shell py-6 md:py-8">
      <div className="mb-5 flex flex-col gap-4 rounded-[2rem] border border-white/70 bg-white/80 p-5 shadow-[0_20px_60px_-24px_rgba(15,23,42,0.22)] md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <Link href={`/documents/${documentId}`}>
            <Button variant="outline" size="sm" className="rounded-full border-white/70 bg-white/80">
              <ArrowLeft className="mr-1 h-4 w-4" />
              返回
            </Button>
          </Link>
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              <ScanText className="h-3.5 w-3.5" />
              {document.file_type === "pdf" ? "PDF 多页阅读器" : "单页图像阅读器"}
            </div>
            <h1 className="max-w-3xl text-xl font-semibold text-slate-900 md:text-2xl">
              {document.original_filename}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              共 {document.page_count} 页 · 当前第 {currentPageNumber} 页 · {blocks.length} 个区块
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant={readingMode === "page" ? "default" : "outline"}
            size="sm"
            className="rounded-full"
            onClick={() => setReadingMode("page")}
          >
            <FileText className="mr-2 h-4 w-4" />
            当前页
          </Button>
          <Button
            variant={readingMode === "document" ? "default" : "outline"}
            size="sm"
            className="rounded-full"
            onClick={() => setReadingMode("document")}
          >
            <BookText className="mr-2 h-4 w-4" />
            全文
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full border-white/70 bg-white/80"
            onClick={() => setShowBlockList((prev) => !prev)}
          >
            <LayoutPanelLeft className="mr-2 h-4 w-4" />
            {showBlockList ? "隐藏区块列表" : "显示区块列表"}
          </Button>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_26rem]">
        <div className="min-w-0">
          {currentPage && (
            <PageViewer
              page={currentPage}
              blocks={blocks}
              selectedBlockId={selectedBlock?.id || null}
              onBlockSelect={handleBlockSelect}
            />
          )}
          {document.file_type === "pdf" && (
            <PageNavigator
              currentPage={currentPageNumber}
              totalPages={document.page_count}
              onPageChange={handlePageChange}
            />
          )}
        </div>

        <div className="flex min-h-[720px] flex-col overflow-hidden rounded-[2rem] border border-white/70 bg-white/85 shadow-[0_20px_60px_-24px_rgba(15,23,42,0.22)]">
          {showBlockList && readingMode === "page" && (
            <div className="border-b border-slate-200/80 px-5 py-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-base font-semibold text-slate-900">区块目录</h3>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                  {blocks.length} blocks
                </span>
              </div>
              <div className="max-h-60 space-y-2 overflow-auto pr-1">
                {blocks.map((block) => (
                  <button
                    key={block.id}
                    type="button"
                    className={cn(
                      "w-full rounded-2xl border px-4 py-3 text-left transition-all",
                      selectedBlock?.id === block.id
                        ? "border-primary/20 bg-primary/10 shadow-sm"
                        : "border-slate-200 bg-white hover:border-primary/20 hover:bg-slate-50"
                    )}
                    onClick={() => handleBlockSelect(block)}
                  >
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-slate-900">区块 {block.block_index + 1}</span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
                        {block.block_label || "text"}
                      </span>
                    </div>
                    <p className="line-clamp-2 text-sm leading-6 text-slate-500">
                      {block.ocr_text_raw || "无文本内容"}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="min-h-0 flex-1">
            {readingMode === "document" ? (
              <div className="flex h-full flex-col bg-white/70">
                <div className="border-b border-slate-200 px-5 py-5">
                  <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                    <BookText className="h-3.5 w-3.5" />
                    {document.file_type === "pdf" ? "分页全文 OCR" : "坐标顺序全文 OCR"}
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900">
                    {document.file_type === "pdf" ? `第 ${currentPageNumber} 页全文` : "整页区块顺序结果"}
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    {document.file_type === "pdf"
                      ? "PDF 全文模式按当前页展示，便于逐页对照原文，并可在底部继续翻页。"
                      : "图片全文模式按原始区块坐标顺序排列，便于和原文位置对照。"}
                  </p>
                </div>
                <div className="flex-1 overflow-auto px-5 py-5">
                  <div className="rounded-[1.5rem] border border-slate-200 bg-white p-5 shadow-sm">
                    {orderedBlockTexts.length > 0 ? (
                      <div className="prose prose-sm max-w-none text-slate-700">
                        <p className="whitespace-pre-wrap leading-7">
                          {orderedBlockTexts.map((block) => block.text).join("\n\n")}
                        </p>
                      </div>
                    ) : fullMarkdown ? (
                      <div className="prose prose-sm max-w-none text-slate-700">
                        <p className="whitespace-pre-wrap leading-7">{fullMarkdown}</p>
                      </div>
                    ) : (
                      <p className="text-sm italic text-slate-400">暂无全文 OCR 结果</p>
                    )}
                  </div>
                </div>
                {document.file_type === "pdf" && (
                  <div className="border-t border-slate-200 px-5 py-4">
                    <PageNavigator
                      currentPage={currentPageNumber}
                      totalPages={document.page_count}
                      onPageChange={handlePageChange}
                    />
                  </div>
                )}
              </div>
            ) : (
              <BlockPanel
                block={selectedBlock}
                pageMarkdown={currentPageMarkdown}
                onPagePolish={handlePagePolish}
                onDocumentPolish={handleDocumentPolish}
                isPolishing={isPolishing}
                activeTask={activeTask}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
