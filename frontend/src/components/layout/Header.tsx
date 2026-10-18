"use client";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { BookOpen } from "lucide-react";
export function Header() {
  const pathname = usePathname();
  const headerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const update = () =>
      document.documentElement.style.setProperty(
        "--app-header-height",
        `${el.getBoundingClientRect().height}px`,
      );
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return (
    <header
      ref={headerRef}
      className="site-header sticky top-0 z-50 border-b bg-background/95"
    >
      <div className="app-shell flex flex-col gap-3 py-4 md:flex-row md:items-center md:justify-between">
        <Link href="/" className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <BookOpen className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold tracking-[.08em]">
              广州商馆档案
            </p>
            <p className="mt-1 text-[9px] uppercase tracking-[.16em] text-muted-foreground">
              Canton Archives · Research
            </p>
          </div>
        </Link>
        <nav
          aria-label="主导航"
          className="flex gap-4 overflow-x-auto sm:gap-7"
        >
          {[
            ["/", "工作台"],
            ["/documents", "档案库"],
            ["/research", "证据检索"],
            ["/knowledge", "知识库"],
            ["/reviews", "审核"],
          ].map(([href, label]) => {
            const active =
              href === "/"
                ? pathname === "/"
                : pathname.startsWith(href) ||
                  (href === "/documents" &&
                    (pathname.startsWith("/viewer") || pathname === "/upload"));
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap border-b-2 px-1 py-2 text-[13px] transition ${active ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
