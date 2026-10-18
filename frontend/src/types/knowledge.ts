export interface CorpusDocumentRecord {
  id: number;
  corpus_id: number;
  document_id: number;
  canonical_title?: string;
  volume?: string;
  archive_id?: string;
  date_start?: string;
  date_end?: string;
  missing_pages_note?: string;
  created_at: string;
  updated_at: string;
}

export interface Corpus {
  id: number;
  name: string;
  description?: string;
  date_start?: string;
  date_end?: string;
  source_institution?: string;
  citation?: string;
  completeness_note?: string;
  created_at: string;
  updated_at: string;
  documents: CorpusDocumentRecord[];
}

export interface EvidenceSpan {
  id: number;
  public_id: string;
  document_id: number;
  page_id: number;
  block_id: number;
  text_version: string;
  excerpt: string;
  char_start: number;
  char_end: number;
  created_at: string;
}

export interface EvidenceLocator {
  evidence_span: EvidenceSpan;
  page_number?: number;
  bbox?: number[];
  image_path?: string;
  viewer_path: string;
}

export type EntityType = "person" | "organization" | "place" | "role" | "other";

export interface EntityCreateRequest {
  entity_type: EntityType;
  canonical_name: string;
  notes?: string;
}

export interface CanonicalEntity {
  id: number;
  entity_type: string;
  canonical_name: string;
  notes?: string;
  activity_start?: string;
  activity_end?: string;
  disambiguation_status: string;
  is_inferred: boolean;
  created_at: string;
  updated_at: string;
  names: Array<{ id: number; name: string; name_type: string }>;
}

export interface EntityMention {
  id: number;
  evidence_span_id: number;
  mention_text: string;
  mention_type: string;
  char_start: number;
  char_end: number;
  current_entity_id?: number | null;
  created_at: string;
}

export interface IdentityDecision {
  id: number;
  mention_id: number;
  entity_id?: number | null;
  decision: string;
  rationale?: string;
  is_revoked: boolean;
  created_at: string;
}

export interface EntityDossier extends CanonicalEntity {
  mentions: EntityMention[];
  identity_decisions: IdentityDecision[];
  roles: Array<{
    id: number;
    role_title: string;
    tenure_type: string;
    start_date?: string;
    end_date?: string;
  }>;
}

export interface HistoricalEvent {
  id: number;
  event_type: string;
  title: string;
  summary?: string;
  start_date?: string;
  end_date?: string;
  date_uncertainty_note?: string;
  participants: Array<{
    id: number;
    entity_id: number;
    role: string;
  }>;
}

export interface Assertion {
  id: number;
  subject_entity_id: number;
  predicate: string;
  object_entity_id?: number | null;
  object_literal?: string;
  original_predicate_text?: string;
  source_type: string;
  certainty: string;
  is_inferred: boolean;
  evidence_links: Array<{
    id: number;
    evidence_span_id: number;
    stance: string;
  }>;
}

export interface WorkbenchOverview {
  corpora: number;
  corpus_documents: number;
  evidence_spans: number;
  mentions: number;
  unresolved_mentions: number;
  entities: number;
  events: number;
  assertions: number;
}

export interface KnowledgeListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
