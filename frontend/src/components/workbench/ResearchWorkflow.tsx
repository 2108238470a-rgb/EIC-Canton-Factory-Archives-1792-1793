import Link from "next/link";
export function ResearchWorkflow({
  current,
}: {
  current: "record" | "review" | "knowledge";
}) {
  return (
    <div className="research-workflow">
      <p>一条研究记录如何进入知识库</p>
      <ol>
        <li data-active={current === "record"}>
          <b>1</b>
          <span>
            选原文、写判断
            <small>引句是证据；人物、事件等字段是你的解读。</small>
          </span>
        </li>
        <li data-active={current === "review"}>
          <b>2</b>
          <span>
            <Link href="/reviews">核对来源并审核</Link>
            <small>先看扫描和引句，再逐项通过、修改或驳回。</small>
          </span>
        </li>
        <li data-active={current === "knowledge"}>
          <b>3</b>
          <span>
            <Link href="/knowledge">查看知识档案</Link>
            <small>待审记录可见；通过的字段才形成正式研究判断。</small>
          </span>
        </li>
      </ol>
    </div>
  );
}
