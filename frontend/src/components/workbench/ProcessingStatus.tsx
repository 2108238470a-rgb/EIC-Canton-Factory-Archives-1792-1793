import { Document } from "@/types";
const LABELS: Record<string, string> = {
  not_started: "未润色",
  partial: "部分完成",
  completed: "润色完成",
  running: "润色中",
  pending: "等待润色",
  failed: "润色失败",
  needs_review: "校正候选待核对",
};
export function ProcessingStatus({ document }: { document: Document }) {
  const p = document.processing_summary;
  return (
    <span
      className={`processing-status ${p?.polish_status === "completed" ? "is-complete" : ""}`}
      title="按当前有效 OCR 文本的原文润色覆盖统计"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {p ? LABELS[p.polish_status] || "润色状态未知" : "润色状态加载中"}
      {p && p.text_blocks > 0 && p.polish_status !== "not_started" && (
        <span className="opacity-70">
          {p.polished_blocks}/{p.text_blocks}
        </span>
      )}
    </span>
  );
}
