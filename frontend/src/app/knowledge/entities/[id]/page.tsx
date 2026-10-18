"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { request } from "@/lib/workbench";
export default function LegacyEntityLink() {
  const { id } = useParams();
  const router = useRouter();
  const [error, setError] = useState("");
  useEffect(() => {
    request<{ canonical_id?: number }>(`/entities/${id}`)
      .then((r) => {
        if (!r.canonical_id) throw new Error("此历史人物记录尚待核验");
        router.replace(`/knowledge/dossiers/${r.canonical_id}`);
      })
      .catch((e) => setError(e.message));
  }, [id, router]);
  return (
    <div className="app-shell py-10">
      {error ? (
        <>
          <p className="error-message" role="alert">
            {error}
          </p>
          <Link className="text-primary" href="/knowledge">
            返回知识库
          </Link>
        </>
      ) : (
        <p className="empty-state">正在打开历史人物记录…</p>
      )}
    </div>
  );
}
