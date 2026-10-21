"use client";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";
import {
  BookOpen,
  LayoutDashboard,
  Library,
  MessagesSquare,
  Network,
  ClipboardCheck,
  Plus,
  ArrowUpRight,
} from "lucide-react";
const navigation = [
  { href: "/", label: "研究工作台", icon: LayoutDashboard },
  { href: "/documents", label: "我的文献", icon: Library },
  { href: "/research", label: "研究助手", icon: MessagesSquare },
  { href: "/knowledge", label: "历史知识库", icon: Network },
  { href: "/reviews", label: "审核与校勘", icon: ClipboardCheck },
];
export function Header() {
  const pathname = usePathname();
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const desktop = window.matchMedia("(min-width: 1180px)").matches;
      document.documentElement.style.setProperty(
        "--app-header-height",
        desktop ? "0px" : `${el.getBoundingClientRect().height}px`,
      );
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);
  return (
    <header ref={ref} className="research-navigation">
      <Link href="/" className="research-brand">
        <span className="research-brand-symbol">
          <BookOpen size={23} strokeWidth={1.5} />
        </span>
        <span>
          <strong>广州商馆档案</strong>
          <small>EIC CANTON ARCHIVES</small>
        </span>
      </Link>
      <div className="navigation-caption">
        研究空间 <span>WORKSPACE</span>
      </div>
      <nav aria-label="主导航" className="research-nav-links">
        {navigation.map(({ href, label, icon: Icon }) => {
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
            >
              <Icon size={18} strokeWidth={1.6} />
              <span>{label}</span>
              {active && <i />}
            </Link>
          );
        })}
      </nav>
      <Link className="navigation-import" href="/upload">
        <Plus size={17} />
        导入新文献
      </Link>
      <div className="navigation-footer">
        <div className="navigation-note">
          <span className="navigation-note-rule" />
          <p>
            每一次发现
            <br />
            都回到原始证据。
          </p>
          <small>READ · DISCOVER · VERIFY</small>
        </div>
        <div className="navigation-bottom">
          <Link href="/documents">
            档案研究平台 <ArrowUpRight size={12} />
          </Link>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
