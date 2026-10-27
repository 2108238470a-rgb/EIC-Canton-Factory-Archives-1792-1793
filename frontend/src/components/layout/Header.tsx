"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { FileText, Upload, Home, Sparkles, GitFork, ShieldCheck, MessageSquare, Bot, FlaskConical, Library, ScrollText, ClipboardCheck } from "lucide-react";

export function Header() {
  const pathname = usePathname();

  const navItems = [
    { href: "/", label: "首页", icon: Home },
    { href: "/upload", label: "上传", icon: Upload },
    { href: "/documents", label: "文档列表", icon: FileText },
    { href: "/kg/graph", label: "人物图谱", icon: GitFork },
    { href: "/kg/review", label: "知识审核", icon: ShieldCheck },
    { href: "/kg/workflow", label: "研究流程", icon: FlaskConical },
    { href: "/rag", label: "智能问答", icon: MessageSquare },
    { href: "/agent", label: "AI 研究员", icon: Bot },
    // V2 knowledge workbench (merged from upstream): entries live on the same pill row
    // so the new pages are reachable at all — they were URL-only before.
    { href: "/knowledge", label: "知识库", icon: Library },
    { href: "/research", label: "研究档案", icon: ScrollText },
    { href: "/reviews", label: "审核队列", icon: ClipboardCheck },
  ];

  return (
    <header className="sticky top-0 z-50 border-b border-white/60 bg-white/70 backdrop-blur-xl">
      <div className="app-shell flex h-20 items-center justify-between gap-6">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-medium text-primary/80">Digital Humanities OCR</p>
            <p className="text-lg font-semibold tracking-tight text-slate-900">OCR 翻译平台</p>
          </div>
        </Link>

        <nav className="flex max-w-[70vw] items-center gap-1 overflow-x-auto rounded-full border border-white/70 bg-white/75 p-1.5 shadow-sm lg:gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex shrink-0 items-center gap-2 rounded-full px-3 py-2 text-sm font-medium transition-all lg:px-4",
                  isActive
                    ? "bg-slate-900 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
