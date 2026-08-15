import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/layout/Header";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "OCR 翻译平台",
  description: "历史文献 OCR 识别、对照阅读与翻译平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <div className="relative min-h-screen overflow-hidden">
          <div className="absolute inset-x-0 top-0 -z-10 h-[32rem] bg-[radial-gradient(circle_at_top,rgba(99,102,241,0.18),transparent_55%)]" />
          <div className="absolute inset-x-0 top-32 -z-10 h-[28rem] bg-[radial-gradient(circle_at_center,rgba(14,165,233,0.12),transparent_45%)]" />
          <div className="relative flex min-h-screen flex-col">
            <Header />
            <main className="flex-1">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
