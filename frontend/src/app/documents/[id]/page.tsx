"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { documentApi, taskApi, exportApi } from "@/lib/api";
import { Document, Task, Page } from "@/types";
import {
  formatFileSize,
  formatDate,
  getStatusColor,
  getStatusText,
  getOcrStageText,
} from "@/lib/utils";
import {
  FileText,
  Play,
  Eye,
  Download,
  Loader2,
  RefreshCw,
  Clock3,
  Files,
} from "lucide-react";

export default function DocumentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const documentId = Number(params.id);

  const [document, setDocument] = useState<Document | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [loading, setLoading] = useState(true);
  const [task, setTask] = useState<Task | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const fetchDocument = async () => {
    try {
      const doc = await documentApi.get(documentId);
      setDocument(doc);

      if (doc.page_count > 0) {
        const pagesResponse = await documentApi.getPages(documentId);
        setPages(pagesResponse.items);
      }
    } catch (error) {
      console.error("Failed to fetch document:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocument();
  }, [documentId]);

  const handleRunOcr = async () => {
    setIsProcessing(true);
    try {
      const newTask = await documentApi.runOcr(documentId);
      setTask(newTask);

      await taskApi.poll(newTask.id, (updatedTask) => {
        setTask(updatedTask);
      });

      await fetchDocument();
    } catch (error) {
      console.error("OCR failed:", error);
    } finally {
      setIsProcessing(false);
      setTask(null);
    }
  };

  const handleExport = async (
    format: "json" | "markdown" | "txt" | "docx",
    textMode?: "ocr_raw" | "llm_polished",
  ) => {
    try {
      const exportResult = await exportApi.create(documentId, {
        format,
        text_mode: textMode,
      });
      if (exportResult.status === "completed" && exportResult.file_path) {
        window.open(exportApi.getDownloadUrl(exportResult.id), "_blank");
      }
    } catch (error) {
      console.error("Export failed:", error);
    }
  };

  if (loading) {
    return (
      <div className="container py-10 flex justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (!document) {
    return (
      <div className="container py-10 text-center">
        <p>文档不存在</p>
        <Link href="/documents">
          <Button className="mt-4">返回列表</Button>
        </Link>
      </div>
    );
  }

  const taskStageText = getOcrStageText(task?.result);
  const currentPageNumber = task?.result?.page_number;
  const totalPageCount = task?.result?.page_count || document.page_count;

  return (
    <div className="container py-10">
      <div className="mb-6">
        <Link
          href="/documents"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← 返回列表
        </Link>
      </div>

      <Link
        href={`/documents/${documentId}/workspace`}
        className="mb-6 flex items-center justify-between rounded-lg border bg-card p-5 text-primary hover:bg-accent"
      >
        <span>
          <strong className="block">进入文献研究工作区</strong>
          <span className="mt-1 block text-xs text-muted-foreground">
            智能目录 · 文献概览 · 事件时间线 · 原文核验
          </span>
        </span>
        <span>→</span>
      </Link>
      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center space-x-2">
                  <FileText className="h-6 w-6" />
                  <span>{document.original_filename}</span>
                </CardTitle>
                <span
                  className={`px-3 py-1 rounded-full text-sm ${getStatusColor(document.status)}`}
                >
                  {getStatusText(document.status)}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">文件大小：</span>
                  <span>{formatFileSize(document.file_size)}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">文件类型：</span>
                  <span>{document.file_type.toUpperCase()}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">页数：</span>
                  <span>{document.page_count}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">创建时间：</span>
                  <span>{formatDate(document.created_at)}</span>
                </div>
              </div>

              {document.error_message && (
                <div className="mt-4 p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
                  {document.error_message}
                </div>
              )}

              {task && (
                <div className="mt-5 space-y-4 rounded-md border border-primary/15 bg-primary/5 p-4">
                  <div className="flex items-center justify-between text-sm font-medium text-slate-700">
                    <span>处理进度</span>
                    <span>{task.progress}%</span>
                  </div>
                  <Progress value={task.progress} />
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl bg-white/80 p-3 text-sm text-slate-600 shadow-sm">
                      <div className="mb-1 inline-flex items-center gap-2 text-slate-900">
                        <Clock3 className="h-4 w-4 text-primary" />
                        当前阶段
                      </div>
                      <p>{taskStageText}</p>
                    </div>
                    <div className="rounded-xl bg-white/80 p-3 text-sm text-slate-600 shadow-sm">
                      <div className="mb-1 inline-flex items-center gap-2 text-slate-900">
                        <Files className="h-4 w-4 text-primary" />
                        页面进度
                      </div>
                      <p>
                        {typeof currentPageNumber === "number" && totalPageCount
                          ? `当前处理第 ${currentPageNumber} / ${totalPageCount} 页`
                          : totalPageCount
                            ? `本次任务共 ${totalPageCount} 页`
                            : "正在等待页数信息"}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {pages.length > 0 && (
            <Card className="mt-6">
              <CardHeader>
                <CardTitle>页面列表</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-4 gap-4">
                  {pages.map((page) => (
                    <Link
                      key={page.id}
                      href={`/viewer/${documentId}?page=${page.page_number}`}
                      className="border rounded-lg p-2 hover:border-primary transition-colors"
                    >
                      <div className="aspect-[3/4] bg-muted rounded flex items-center justify-center mb-2">
                        <FileText className="h-8 w-8 text-muted-foreground" />
                      </div>
                      <p className="text-sm text-center">
                        第 {page.page_number} 页
                      </p>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>操作</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {document.status === "pending" && (
                <Button
                  className="w-full"
                  onClick={handleRunOcr}
                  disabled={isProcessing}
                >
                  {isProcessing ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-2 h-4 w-4" />
                  )}
                  开始 OCR
                </Button>
              )}

              {(document.status === "ocr_completed" ||
                document.status === "completed") && (
                <>
                  <Link href={`/viewer/${documentId}`} className="block">
                    <Button className="w-full" variant="outline">
                      <Eye className="mr-2 h-4 w-4" />
                      查看阅读器
                    </Button>
                  </Link>

                  <Button
                    className="w-full"
                    variant="outline"
                    onClick={handleRunOcr}
                    disabled={isProcessing}
                  >
                    <RefreshCw className="mr-2 h-4 w-4" />
                    重新 OCR
                  </Button>
                </>
              )}
            </CardContent>
          </Card>

          {(document.status === "ocr_completed" ||
            document.status === "completed") && (
            <Card>
              <CardHeader>
                <CardTitle>导出</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => handleExport("json")}
                >
                  <Download className="mr-2 h-4 w-4" />
                  导出 JSON
                </Button>
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => handleExport("markdown")}
                >
                  <Download className="mr-2 h-4 w-4" />
                  导出 Markdown
                </Button>
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => handleExport("txt")}
                >
                  <Download className="mr-2 h-4 w-4" />
                  导出 TXT
                </Button>
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => handleExport("docx", "ocr_raw")}
                >
                  <Download className="mr-2 h-4 w-4" />
                  导出 DOCX（OCR 原文）
                </Button>
                <Button
                  className="w-full"
                  variant="outline"
                  onClick={() => handleExport("docx", "llm_polished")}
                >
                  <Download className="mr-2 h-4 w-4" />
                  导出 DOCX（OCR 纠错）
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
