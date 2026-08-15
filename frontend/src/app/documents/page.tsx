"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { documentApi } from "@/lib/api";
import { Document } from "@/types";
import { formatFileSize, formatDate, getStatusColor, getStatusText } from "@/lib/utils";
import { FileText, Eye, Trash2, Loader2, RefreshCw, ArrowRight } from "lucide-react";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const response = await documentApi.list(page, pageSize);
      setDocuments(response.items);
      setTotal(response.total);
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [page]);

  const handleDelete = async (id: number) => {
    if (!confirm("确定要删除这个文档吗？")) return;
    try {
      await documentApi.delete(id);
      fetchDocuments();
    } catch (error) {
      console.error("Failed to delete document:", error);
    }
  };

  if (loading) {
    return (
      <div className="app-shell flex justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="app-shell py-10 md:py-14">
      <div className="mb-8 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="mb-3 text-sm font-medium uppercase tracking-[0.24em] text-primary/70">Workspace</p>
          <h1 className="section-title">文档列表</h1>
          <p className="section-description mt-3">查看上传记录、OCR 状态、页数信息，并进入阅读器进行对照与加工。</p>
        </div>
        <Button variant="outline" onClick={fetchDocuments} className="rounded-full border-white/70 bg-white/80 px-5">
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新列表
        </Button>
      </div>

      {documents.length === 0 ? (
        <Card className="soft-card border-0">
          <CardContent className="flex flex-col items-center py-16 text-center">
            <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-3xl bg-primary/10 text-primary">
              <FileText className="h-8 w-8" />
            </div>
            <p className="text-xl font-semibold text-slate-900">暂无文档</p>
            <p className="mt-2 max-w-md text-sm text-slate-500">上传第一份文档后，这里会展示 OCR、译校和阅读入口。</p>
            <Link href="/upload">
              <Button className="mt-6 rounded-full px-6 shadow-lg shadow-primary/20">上传文档</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {documents.map((doc) => (
            <Card key={doc.id} className="soft-card border-0">
              <CardContent className="p-5">
                <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
                  <div className="flex items-start gap-4">
                    <div className="flex h-14 w-14 items-center justify-center rounded-3xl bg-primary/10 text-primary">
                      <FileText className="h-7 w-7" />
                    </div>
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <h3 className="text-lg font-semibold text-slate-900">{doc.original_filename}</h3>
                        <span className={`rounded-full px-3 py-1 text-xs font-medium ${getStatusColor(doc.status)}`}>
                          {getStatusText(doc.status)}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-4 text-sm text-slate-500">
                        <span>{formatFileSize(doc.file_size)}</span>
                        <span>{doc.page_count} 页</span>
                        <span>{formatDate(doc.created_at)}</span>
                        <span className="capitalize">{doc.file_type}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/documents/${doc.id}`}>
                      <Button variant="outline" size="sm" className="rounded-full border-white/70 bg-white/80">
                        详情
                      </Button>
                    </Link>
                    {(doc.status === "ocr_completed" || doc.status === "completed") && (
                      <Link href={`/viewer/${doc.id}`}>
                        <Button size="sm" className="rounded-full shadow-lg shadow-primary/20">
                          <Eye className="mr-1 h-4 w-4" />
                          进入阅读器
                        </Button>
                      </Link>
                    )}
                    <Button variant="ghost" size="sm" className="rounded-full" onClick={() => handleDelete(doc.id)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {total > pageSize && (
            <div className="mt-8 flex items-center justify-center gap-3">
              <Button variant="outline" className="rounded-full border-white/70 bg-white/80" disabled={page === 1} onClick={() => setPage(page - 1)}>
                上一页
              </Button>
              <div className="rounded-full border border-white/70 bg-white/80 px-4 py-2 text-sm text-slate-600">
                {page} / {Math.ceil(total / pageSize)}
              </div>
              <Button variant="outline" className="rounded-full border-white/70 bg-white/80" disabled={page >= Math.ceil(total / pageSize)} onClick={() => setPage(page + 1)}>
                下一页
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
