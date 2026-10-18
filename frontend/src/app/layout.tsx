import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/layout/Header";
export const metadata: Metadata = {
  title: "广州商馆档案 · 历史知识工作台",
  description: "档案阅读、证据标注、知识复核与研究检索",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="flex min-h-screen flex-col">
          <Header />
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
