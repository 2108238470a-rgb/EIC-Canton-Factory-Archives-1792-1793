"use client";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import { Evidence, STATE_LABELS } from "@/types/workbench";
import { apiUrl } from "@/lib/workbench";
import { Button } from "@/components/ui/button";
export function EvidenceContent({ evidence: e }: { evidence: Evidence }) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="status-badge">
          {STATE_LABELS[e.validity] || e.validity}
        </span>
        <span>
          {e.archival_reference || e.document_title} · PDF {e.page_number} ·
          原档 {e.original_page_label || "未录入"} {e.folio_side || ""}
        </span>
      </div>
      <blockquote className="border-l-2 border-primary/40 bg-muted/40 p-4 text-sm leading-7 whitespace-pre-wrap">
        {e.excerpt}
      </blockquote>
      {e.revision_content && (
        <details className="text-sm">
          <summary className="cursor-pointer text-primary">
            完整文本版本与 OCR 对照
          </summary>
          <div className="mt-3 space-y-3">
            <div>
              <h3 className="mb-2 text-xs text-muted-foreground">
                引用所依文本版本 #{e.revision_id}
              </h3>
              <p className="max-h-72 overflow-auto whitespace-pre-wrap rounded border p-3 text-sm leading-7">
                {e.revision_content}
              </p>
            </div>
            {e.raw_revision_content && e.raw_revision_id !== e.revision_id && (
              <div>
                <h3 className="mb-2 text-xs text-muted-foreground">
                  同区块历史 OCR #{e.raw_revision_id}（对照）
                </h3>
                <p className="max-h-72 overflow-auto whitespace-pre-wrap rounded border p-3 text-sm leading-7">
                  {e.raw_revision_content}
                </p>
              </div>
            )}
          </div>
        </details>
      )}
      <p className="text-xs text-muted-foreground">
        文本版本 {e.revision_id} · 图像高亮精度：区块
      </p>
      {e.validity !== "current" ? (
        <p className="notice">
          {e.image_frozen
            ? "该证据指向历史文本与保存的原始图像版本，正式研究前需重新验证。"
            : "该证据指向历史文本，当前页图仅供对照，需重新验证图像位置。"}
        </p>
      ) : null}
      {imageFailed ? (
        <p role="alert" className="notice">
          原图暂不可用，请在阅读器中重试。
        </p>
      ) : (
        <div className="relative overflow-hidden border bg-stone-100">
          <img
            src={apiUrl(e.image_url)}
            alt={`档案第 ${e.page_number} 页`}
            onError={() => setImageFailed(true)}
            className="h-auto w-full"
          />
          {e.bbox &&
          e.image_width &&
          e.image_height &&
          (e.validity === "current" || e.image_frozen) ? (
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox={`0 0 ${e.image_width} ${e.image_height}`}
            >
              <rect
                x={e.bbox[0]}
                y={e.bbox[1]}
                width={e.bbox[2] - e.bbox[0]}
                height={e.bbox[3] - e.bbox[1]}
                fill="rgba(84,92,141,.15)"
                stroke="#545c8d"
                strokeWidth="3"
              />
            </svg>
          ) : null}
        </div>
      )}
      <Link
        className="text-sm text-primary underline underline-offset-4"
        href={e.viewer_path}
      >
        打开原图阅读器 →
      </Link>
    </div>
  );
}
export function EvidenceDialog({
  evidence,
  label = "核对证据",
}: {
  evidence: Evidence[];
  label?: string;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <Button variant="outline" size="sm" disabled={!evidence.length}>
          {label}
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-slate-950/30" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[61] max-h-[90vh] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border bg-background p-6 shadow-lg">
          <div className="mb-5 flex justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold">
                原文与来源
              </Dialog.Title>
              <Dialog.Description className="text-sm text-muted-foreground">
                逐条核对引句、文本版本及档案位置。
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="outline" size="sm">
                关闭
              </Button>
            </Dialog.Close>
          </div>
          <div className="space-y-8">
            {evidence.map((e) => (
              <EvidenceContent key={e.id} evidence={e} />
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
