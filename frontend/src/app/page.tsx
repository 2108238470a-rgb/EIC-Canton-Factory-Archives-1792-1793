import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, FileText, Eye, Download, ArrowRight, Sparkles, ScanText, Languages } from "lucide-react";

const features = [
  {
    icon: Upload,
    title: "多格式上传",
    description: "支持 PDF 与历史文献图片上传，快速进入 OCR 流程。",
  },
  {
    icon: ScanText,
    title: "版面解析 + OCR",
    description: "基于 PaddleOCR-VL 进行页面识别、结构化提取与可视化。",
  },
  {
    icon: Languages,
    title: "智能译校",
    description: "支持 OCR 纠错、现代英语重写和中文翻译的多阶段加工。",
  },
  {
    icon: Download,
    title: "结构化导出",
    description: "将结果导出为 JSON、Markdown 与 TXT，便于再利用。",
  },
];

export default function Home() {
  return (
    <div className="app-shell py-10 md:py-16">
      <section className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
        <div className="space-y-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/10 px-4 py-2 text-sm font-medium text-primary">
            <Sparkles className="h-4 w-4" />
            面向文献 OCR、译校与阅读比对的一体化工作台
          </div>

          <div className="space-y-5">
            <h1 className="max-w-4xl text-5xl font-semibold tracking-tight text-slate-950 md:text-6xl">
              让历史文献的识别、整理与阅读体验更顺滑。
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-slate-600">
              上传扫描件或 PDF，自动完成版面分析、OCR、文本加工与对照阅读。
              适合数字人文、史料整理与学术研究场景。
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <Link href="/upload">
              <Button size="lg" className="rounded-full px-6 shadow-lg shadow-primary/20">
                <Upload className="mr-2 h-4 w-4" />
                开始上传
              </Button>
            </Link>
            <Link href="/documents">
              <Button variant="outline" size="lg" className="rounded-full border-white/70 bg-white/80 px-6">
                <Eye className="mr-2 h-4 w-4" />
                查看文档
              </Button>
            </Link>
          </div>
        </div>

        <div className="soft-card overflow-hidden p-6 md:p-8">
          <div className="rounded-[1.75rem] border border-slate-200 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-900/15">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-400">Reader Workspace</p>
                <h2 className="mt-1 text-2xl font-semibold">图像与文本双栏对照</h2>
              </div>
              <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                OCR + GPT
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="mb-3 flex items-center justify-between text-xs text-slate-300">
                  <span>Page Preview</span>
                  <span>12 blocks</span>
                </div>
                <div className="h-56 rounded-xl bg-gradient-to-br from-slate-700 via-slate-800 to-slate-900 p-4">
                  <div className="h-full rounded-lg border border-dashed border-primary/40 bg-primary/10" />
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="mb-3 flex items-center justify-between text-xs text-slate-300">
                  <span>Text Workspace</span>
                  <span>现代产品感</span>
                </div>
                <div className="space-y-3 rounded-xl bg-white/5 p-4">
                  <div className="h-3 w-20 rounded-full bg-primary/60" />
                  <div className="h-3 w-full rounded-full bg-white/15" />
                  <div className="h-3 w-5/6 rounded-full bg-white/15" />
                  <div className="h-3 w-2/3 rounded-full bg-white/15" />
                </div>
                <div className="mt-4 inline-flex items-center text-sm text-primary-foreground/90">
                  浏览阅读器
                  <ArrowRight className="ml-2 h-4 w-4" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-14 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <Card key={feature.title} className="soft-card border-0">
              <CardHeader className="space-y-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Icon className="h-6 w-6" />
                </div>
                <div>
                  <CardTitle className="text-xl text-slate-900">{feature.title}</CardTitle>
                  <CardDescription className="mt-2 text-sm leading-6 text-slate-600">
                    {feature.description}
                  </CardDescription>
                </div>
              </CardHeader>
            </Card>
          );
        })}
      </section>

      <section className="mt-14 rounded-[2rem] border border-white/70 bg-white/80 p-8 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.28)] md:p-10">
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="space-y-2">
            <h2 className="section-title">从 OCR 到阅读交付，尽量少切换上下文</h2>
            <p className="section-description max-w-2xl">
              上传、识别、译校、查看与导出都集中在一个工作台里，减少手动搬运结果的成本。
            </p>
          </div>
          <Link href="/documents">
            <Button variant="outline" size="lg" className="rounded-full border-slate-200 bg-slate-50 px-6">
              <FileText className="mr-2 h-4 w-4" />
              进入文档列表
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
