export interface Evidence {
  id: number;
  public_id: string;
  revision_id: number;
  text_version: string;
  excerpt: string;
  revision_content?: string;
  raw_revision_content?: string;
  raw_revision_id?: number;
  validity: string;
  block_id: number;
  page_id: number;
  document_id: number;
  document_title: string;
  page_number: number;
  char_start: number;
  char_end: number;
  original_page_label?: string;
  folio_side?: string;
  archival_reference?: string;
  bbox?: number[];
  image_width?: number;
  image_height?: number;
  image_url: string;
  image_frozen?: boolean;
  viewer_path: string;
}
export interface Annotation {
  id: number;
  public_id: string;
  document_id: number;
  source_unit_id?: number;
  source_title?: string;
  evidence_ids: number[];
  evidence: Evidence[];
  fields: Record<string, string>;
  field_states: Record<string, string>;
  entity_links?: Record<string, number>;
  status: string;
  version: number;
  entity_id?: number;
  event_id?: number;
  archival_year?: string;
  history: Array<{
    id: number;
    field: string;
    decision: string;
    reviewer: string;
    reason: string;
    created_at: string;
    value: string;
  }>;
}
export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Extraction {
  id: number;
  status: string;
  error_message?: string;
  output_summary?: { created: number; rejected_candidates: unknown[] };
}
export interface Scope {
  answer_style?: "research" | "guide";
  document_id?: number;
  document_ids?: number[];
  corpus_id?: number;
  date_start?: string;
  date_end?: string;
  entity_id?: number;
  unit_type?: string;
  mode: "verified" | "explore";
  retrieval?: "keyword" | "semantic" | "hybrid";
}
export interface Hit {
  chunk_id: number;
  block_id: number;
  document_id: number;
  document_title: string;
  page_number: number;
  content: string;
  viewer_path: string;
  score: number;
  evidence: Evidence[];
  review_state: string;
  content_type: string;
}
export interface Answer {
  answer_style?: "research" | "guide";
  scope?: Scope;
  sections?: Array<{ title: string; content: string }>;
  outcome?: string;
  diagnostics?: { retrieved?: number; sampling?: boolean; mode?: string };
  answer: string;
  insufficient_evidence: boolean;
  citations: Array<Hit & { index: number; cited: boolean }>;
  claims: Array<{
    kind?: "source_record" | "interpretation";
    text: string;
    citations: number[];
    quotes: string[];
  }>;
  warnings: string[];
  model: string;
}
export const FIELD_LABELS: Record<string, string> = {
  document_date: "文书日期",
  person: "人名",
  name_form: "人名形式",
  honorific: "敬称或称号",
  nationality: "国籍",
  occupation: "职业",
  organization: "人物所属机构",
  title: "当时职务",
  event: "事件",
  event_date: "事件日期",
  role: "参与角色",
  location: "地点",
  related_event: "相关事件",
  notes: "备注",
};
export const STATE_LABELS: Record<string, string> = {
  pending: "待审核",
  approved: "已通过",
  verified: "已复核",
  rejected: "已驳回",
  needs_validation: "需重新验证",
  current: "当前版本",
  stale: "证据已失效",
  legacy_unverified: "历史版本待核验",
  confirmed: "已确认",
  candidate: "候选",
  disputed: "有争议",
};
