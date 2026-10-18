export interface IndexDocument {
  corpus_id?: number | null;
  id: number;
  title: string;
  page_count: number;
  ocr_pages: number;
  eligible: number;
  indexed: number;
  status: string;
}
export interface RagIndexStatus {
  eligible: number;
  indexed: number;
  pending: number;
  embedding_model: string;
  vector_pending?: number;
}

export interface RagIndexJob {
  task_id: string;
  state: string;
  info?: {
    documents_done?: number;
    documents_total?: number;
    done?: number;
    total?: number;
    error?: string;
    indexed?: number;
    vector_failed?: number;
  } | null;
}

export interface RagSearchHit {
  chunk_id: number;
  block_id: number;
  document_id: number;
  document_title: string;
  page_number: number;
  content: string;
  score: number;
  viewer_path: string;
}

export interface RagSearchResponse {
  query: string;
  items: RagSearchHit[];
}

export interface RagCitation extends RagSearchHit {
  index: number;
  cited: boolean;
}

export interface RagAnswer {
  question: string;
  answer: string;
  insufficient_evidence: boolean;
  citations: RagCitation[];
  model: string;
}
