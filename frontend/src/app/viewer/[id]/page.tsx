"use client";

import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { documentApi, pageApi, blockApi, taskApi } from "@/lib/api";
import { Document, Page, Block, Task } from "@/types";
import { PageViewer } from "@/components/viewer/PageViewer";
import { BlockPanel } from "@/components/viewer/BlockPanel";
import { PageNavigator } from "@/components/viewer/PageNavigator";
import {
  ArrowLeft,
  Loader2,
  LayoutPanelLeft,
  ScanText,
  BookText,
  FileText,
} from "lucide-react";
import { apiUrl, request } from "@/lib/workbench";
import { Evidence } from "@/types/workbench";
import { EvidenceDialog } from "@/components/workbench/EvidenceDialog";
import { AnnotationPanel } from "@/components/workbench/AnnotationPanel";
import { cn } from "@/lib/utils";

export default function ViewerPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const documentId = Number(params.id);
  const initialPage = Number(searchParams.get("page")) || 1;
  const initialBlockId = Number(searchParams.get("block")) || null;
  const appliedBlockQuery = useRef(false);
  const evidenceId = Number(searchParams.get("evidence")) || null;
  const [linkedEvidence, setLinkedEvidence] = useState<Evidence | null>(null);
  const [evidenceError, setEvidenceError] = useState("");

  const [document, setDocument] = useState<Document | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [currentPageNumber, setCurrentPageNumber] = useState(initialPage);
  const [currentPage, setCurrentPage] = useState<Page | null>(null);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [selectedBlock, setSelectedBlock] = useState<Block | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPolishing, setIsPolishing] = useState(false);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [mobilePanel, setMobilePanel] = useState<
    "image" | "text" | "knowledge"
  >(
    searchParams.get("from_annotation") || searchParams.get("annotate_revision")
      ? "knowledge"
      : "image",
  );
  const [showBlockList, setShowBlockList] = useState(true);
  const [imageWeight, setImageWeight] = useState(1);
  const [knowledgeWeight, setKnowledgeWeight] = useState(0.9);
  useEffect(() => {
    try {
      const v = JSON.parse(localStorage.getItem("eic-reader-widths") || "null");
      if (v) {
        setImageWeight(v[0]);
        setKnowledgeWeight(v[1]);
      }
    } catch {}
  }, []);
  const [originalFont, setOriginalFont] = useState("sans");
  useEffect(() => {
    setOriginalFont(localStorage.getItem("eic-original-font") || "sans");
  }, []);
  useEffect(() => {
    if (
      currentPage?.document_id === documentId &&
      currentPage.page_number === currentPageNumber
    )
      localStorage.setItem(
        `eic-reading-page-${documentId}`,
        String(currentPageNumber),
      );
  }, [currentPage, documentId, currentPageNumber]);
  const [readingMode, setReadingMode] = useState<"page" | "document">("page");

  useEffect(() => {
    appliedBlockQuery.current = false;
    const saved = searchParams.get("page")
      ? initialPage
      : Number(localStorage.getItem(`eic-reading-page-${documentId}`)) ||
        initialPage;
    setCurrentPageNumber(saved);
    setLinkedEvidence(null);
    setEvidenceError("");
    if (evidenceId)
      request<Evidence>(`/workbench/evidence/${evidenceId}`)
        .then((e) => {
          if (e.document_id !== documentId) throw new Error("证据不属于此文档");
          setLinkedEvidence(e);
        })
        .catch((e) => setEvidenceError(e.message));
  }, [documentId, initialPage, initialBlockId, evidenceId]);

  const fetchDocumentData = useCallback(async () => {
    const doc = await documentApi.get(documentId);
    setDocument(doc);

    const pagesResponse = await documentApi.getPages(documentId);
    setPages(pagesResponse.items);
    return { doc, pages: pagesResponse.items };
  }, [documentId]);

  const fetchCurrentPageData = useCallback(
    async (pageNumber: number, availablePages?: Page[]) => {
      const pageList = availablePages || pages;
      if (pageList.length === 0) return null;

      const page =
        pageList.find((item) => item.page_number === pageNumber) || pageList[0];
      if (!page) return null;

      const pageDetail = await pageApi.get(page.id);
      const blocksResponse = await pageApi.getBlocks(page.id);
      let nextBlocks = blocksResponse.items;

      if (
        linkedEvidence &&
        linkedEvidence.page_id === page.id &&
        linkedEvidence.validity !== "current"
      ) {
        const archived = await blockApi.get(linkedEvidence.block_id);
        nextBlocks = [
          {
            ...archived,
            bbox: linkedEvidence.bbox || archived.bbox,
            ocr_text_raw: linkedEvidence.excerpt,
            ocr_text_corrected: undefined,
          },
        ];
      }
      setCurrentPage(pageDetail);
      setBlocks(nextBlocks);
      setSelectedBlock((prev) => {
        if (!appliedBlockQuery.current && initialBlockId) {
          const queried = nextBlocks.find((item) => item.id === initialBlockId);
          if (queried) {
            appliedBlockQuery.current = true;
            return queried;
          }
        }
        return (
          nextBlocks.find((item) => item.id === prev?.id) ||
          nextBlocks[0] ||
          null
        );
      });
      return { page: pageDetail, blocks: nextBlocks };
    },
    [pages, initialBlockId, linkedEvidence],
  );

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

  const runPolishTask = useCallback(
    async (
      taskPromise: Promise<Task>,
      refreshScope: "block" | "page" | "document",
      blockId?: number,
    ) => {
      setIsPolishing(true);
      try {
        const task = await taskPromise;
        setActiveTask(task);
        await taskApi.poll(task.id, (updatedTask) => {
          setActiveTask(updatedTask);
        });

        if (refreshScope === "block" && blockId) {
          const updatedBlock = await blockApi.get(blockId);
          setBlocks((prev) =>
            prev.map((item) => (item.id === blockId ? updatedBlock : item)),
          );
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
    },
    [currentPageNumber, fetchCurrentPageData, fetchDocumentData],
  );

  const handlePagePolish = useCallback(async () => {
    if (!currentPage) return;
    await runPolishTask(
      pageApi.runPolish(currentPage.id, { modes: ["ocr_correction"] }),
      "page",
    );
  }, [currentPage, runPolishTask]);

  const handleDocumentPolish = useCallback(async () => {
    await runPolishTask(
      documentApi.runPolish(documentId, { modes: ["ocr_correction"] }),
      "document",
    );
  }, [documentId, runPolishTask]);

  const orderedBlockTexts = useMemo(() => {
    return blocks
      .slice()
      .sort((a, b) => a.block_index - b.block_index)
      .map((block) => ({
        id: block.id,
        label: block.block_label || "text",
        index: block.block_index + 1,
        text: block.ocr_text_corrected || block.ocr_text_raw || "",
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
  const fullMarkdown =
    document.full_markdown ||
    pages
      .map((page) => page.markdown_content || "")
      .filter(Boolean)
      .join("\n\n");

  return (
    <div
      className="app-shell reader-workspace py-4"
      data-original-font={originalFont}
    >
      <div className="mb-3 flex shrink-0 flex-col gap-3 rounded-lg border border-border bg-card p-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <Link href={`/documents/${documentId}`}>
            <Button
              variant="outline"
              size="sm"
              className="rounded-full border-border bg-white/80"
            >
              <ArrowLeft className="mr-1 h-4 w-4" />
              返回
            </Button>
          </Link>
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              <ScanText className="h-3.5 w-3.5" />
              {document.file_type === "pdf"
                ? "PDF 多页阅读器"
                : "单页图像阅读器"}
            </div>
            <h1 className="max-w-3xl break-all text-base font-semibold text-slate-900 md:text-lg">
              {document.original_filename}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              共 {document.page_count} 页 · 当前第 {currentPageNumber} 页 ·{" "}
              {blocks.length} 个区块
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
            className="rounded-full border-border bg-white/80"
            onClick={() => setShowBlockList((prev) => !prev)}
          >
            <LayoutPanelLeft className="mr-2 h-4 w-4" />
            {showBlockList ? "隐藏区块列表" : "显示区块列表"}
          </Button>
        </div>
      </div>

      {evidenceError && (
        <p className="error-message" role="alert">
          {evidenceError}
        </p>
      )}
      {linkedEvidence && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border p-3 text-sm">
          <span>
            {linkedEvidence.validity === "current"
              ? "正在查看引用的证据"
              : "历史证据视图：保留原文版本，当前内容可能已更新"}
          </span>
          <EvidenceDialog evidence={[linkedEvidence]} />
          <Link
            className="text-primary"
            href={`/viewer/${documentId}?page=${currentPageNumber}`}
          >
            返回当前版本
          </Link>
        </div>
      )}
      <nav className="mb-4 flex gap-2 lg:hidden" aria-label="阅读器面板">
        {(
          [
            ["image", "原图"],
            ["text", "原文与译校"],
            ["knowledge", "标注与知识"],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            variant={mobilePanel === key ? "default" : "outline"}
            size="sm"
            onClick={() => setMobilePanel(key)}
          >
            {label}
          </Button>
        ))}
      </nav>
      <div className="mb-3 hidden items-center gap-5 text-xs text-muted-foreground lg:flex">
        <Link
          className="text-primary underline"
          href={`/documents/${documentId}/workspace`}
        >
          文献研究工作区
        </Link>
        <label className="flex items-center gap-2">
          原文字体
          <select
            aria-label="原文英文字体"
            className="rounded border bg-card px-2 py-1"
            value={originalFont}
            onChange={(e) => {
              setOriginalFont(e.target.value);
              localStorage.setItem("eic-original-font", e.target.value);
            }}
          >
            <option value="sans">无衬线</option>
            <option value="serif">衬线</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          原图宽度
          <input
            aria-label="原图栏宽度"
            type="range"
            min="0.5"
            max="2"
            step="0.05"
            value={imageWeight}
            onChange={(e) => {
              const v = Number(e.target.value);
              setImageWeight(v);
              localStorage.setItem(
                "eic-reader-widths",
                JSON.stringify([v, knowledgeWeight]),
              );
            }}
          />
        </label>
        <label className="flex items-center gap-2">
          分析宽度
          <input
            aria-label="分析栏宽度"
            type="range"
            min="0.5"
            max="1.5"
            step="0.05"
            value={knowledgeWeight}
            onChange={(e) => {
              const v = Number(e.target.value);
              setKnowledgeWeight(v);
              localStorage.setItem(
                "eic-reader-widths",
                JSON.stringify([imageWeight, v]),
              );
            }}
          />
        </label>
      </div>
      <div
        style={
          {
            "--reader-template": `minmax(0,${imageWeight}fr) minmax(0,1fr) minmax(0,${knowledgeWeight}fr)`,
          } as React.CSSProperties
        }
        className="reader-columns grid min-h-0 flex-1 gap-3"
      >
        <div
          className={cn(
            "reader-column min-w-0 min-h-0 flex-col",
            mobilePanel === "image" ? "flex" : "hidden lg:flex",
          )}
        >
          {currentPage && (
            <PageViewer
              page={
                linkedEvidence?.image_frozen &&
                linkedEvidence.page_id === currentPage.id
                  ? {
                      ...currentPage,
                      width: linkedEvidence.image_width || currentPage.width,
                      height: linkedEvidence.image_height || currentPage.height,
                    }
                  : currentPage
              }
              imageUrlOverride={
                linkedEvidence?.image_frozen &&
                linkedEvidence.page_id === currentPage.id
                  ? apiUrl(linkedEvidence.image_url)
                  : undefined
              }
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

        <div
          className={cn(
            "reader-column min-w-0 min-h-0 flex-col overflow-hidden rounded-lg border bg-card",
            mobilePanel === "text" ? "flex" : "hidden lg:flex",
          )}
        >
          {showBlockList && readingMode === "page" && (
            <div className="shrink-0 border-b border-slate-200/80 px-4 py-3">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-base font-semibold text-slate-900">
                  区块目录
                </h3>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                  {blocks.length} blocks
                </span>
              </div>
              <div className="max-h-32 space-y-2 overflow-auto overscroll-contain pr-1">
                {blocks.map((block) => (
                  <button
                    key={block.id}
                    type="button"
                    className={cn(
                      "w-full rounded-md border px-4 py-3 text-left transition-all",
                      selectedBlock?.id === block.id
                        ? "border-primary/20 bg-primary/10 shadow-sm"
                        : "border-slate-200 bg-white hover:border-primary/20 hover:bg-slate-50",
                    )}
                    onClick={() => handleBlockSelect(block)}
                  >
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-slate-900">
                        区块 {block.block_index + 1}
                      </span>
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

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            {readingMode === "document" ? (
              <div className="flex min-h-0 h-full flex-col bg-white/70">
                <div className="border-b border-slate-200 px-5 py-5">
                  <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                    <BookText className="h-3.5 w-3.5" />
                    {document.file_type === "pdf"
                      ? "分页全文 OCR"
                      : "坐标顺序全文 OCR"}
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900">
                    {document.file_type === "pdf"
                      ? `第 ${currentPageNumber} 页全文`
                      : "整页区块顺序结果"}
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    {document.file_type === "pdf"
                      ? "PDF 全文模式按当前页展示，便于逐页对照原文，并可在底部继续翻页。"
                      : "图片全文模式按原始区块坐标顺序排列，便于和原文位置对照。"}
                  </p>
                </div>
                <div className="min-h-0 flex-1 overflow-auto overscroll-contain px-5 py-5">
                  <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                    {orderedBlockTexts.length > 0 ? (
                      <div className="prose prose-sm max-w-none text-slate-700">
                        <p className="whitespace-pre-wrap leading-7">
                          {orderedBlockTexts
                            .map((block) => block.text)
                            .join("\n\n")}
                        </p>
                      </div>
                    ) : fullMarkdown ? (
                      <div className="prose prose-sm max-w-none text-slate-700">
                        <p className="whitespace-pre-wrap leading-7">
                          {fullMarkdown}
                        </p>
                      </div>
                    ) : (
                      <p className="text-sm italic text-slate-400">
                        暂无全文 OCR 结果
                      </p>
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
        <div
          className={cn(
            "reader-column min-w-0 min-h-0 overflow-y-auto overscroll-contain",
            mobilePanel !== "knowledge" && "hidden lg:block",
          )}
        >
          {linkedEvidence?.validity !== undefined &&
          linkedEvidence.validity !== "current" ? (
            <div className="panel p-5 text-sm leading-7">
              历史证据保留为只读。返回当前版本后可建立新的替代标注。
            </div>
          ) : (
            <AnnotationPanel
              block={selectedBlock}
              documentId={documentId}
              page={currentPage}
              onBlockUpdated={(updated) => {
                setBlocks((prev) =>
                  prev.map((b) => (b.id === updated.id ? updated : b)),
                );
                setSelectedBlock(updated);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
