import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { RagSearchHit } from "@/types/rag";

interface SourceCardProps {
  hit: RagSearchHit;
  index?: number;
  muted?: boolean;
}

export function SourceCard({ hit, index, muted = false }: SourceCardProps) {
  return (
    <article
      id={index !== undefined ? `source-${index}` : undefined}
      className={cn(
        "rounded-2xl border bg-white px-4 py-3",
        muted ? "border-slate-100 opacity-70" : "border-slate-200"
      )}
    >
      <header className="mb-2 flex items-center justify-between gap-3 text-xs text-slate-500">
        <span>
          {index !== undefined && (
            <span className="mr-2 rounded-full bg-primary/10 px-2 py-0.5 font-semibold text-primary">
              [{index}]
            </span>
          )}
          《{hit.document_title}》第 {hit.page_number} 页
        </span>
        <Link
          href={hit.viewer_path}
          className="inline-flex items-center gap-1 text-primary hover:underline"
        >
          在原文中查看
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </Link>
      </header>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{hit.content}</p>
    </article>
  );
}
