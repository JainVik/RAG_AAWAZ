/**
 * Strict TypeScript API type definitions matching frontend-functional-requirements.md
 * and frontend-backend-change-addendum.md
 */

// ==========================================
// Health & Readiness Types
// ==========================================

export interface HealthResponse {
  status: string;
  version?: string;
  uptime_seconds?: number;
  error?: string;
  [key: string]: unknown;
}

export interface ReadyCheck {
  name: string;
  ready: boolean;
  message?: string;
  details?: Record<string, unknown>;
}

export interface ReadyResponse {
  status: 'ready' | 'not_ready';
  checks: Record<string, boolean | ReadyCheck | { ready?: boolean; message?: string; name?: string }>;
  instance_id?: string;
  started_at?: string;
  runtime?: Record<string, unknown>;
  error?: string;
  deadlines?: {
    hard_ms: number;
    fallback_ms: number;
  };
}

// ==========================================
// Query & Language Enums
// ==========================================

export type LanguageHint =
  | 'unknown'
  | 'auto'
  | 'as'
  | 'bn'
  | 'gu'
  | 'hi'
  | 'en'
  | 'kn'
  | 'ml'
  | 'mr'
  | 'ne'
  | 'or'
  | 'pa'
  | 'sa'
  | 'ta'
  | 'te'
  | 'ur'
  | 'hi-en';

export type Language = LanguageHint;

export type ServerLanguageCode =
  | 'unknown'
  | 'as'
  | 'bn'
  | 'gu'
  | 'hi'
  | 'en'
  | 'kn'
  | 'ml'
  | 'mr'
  | 'ne'
  | 'or'
  | 'pa'
  | 'sa'
  | 'ta'
  | 'te'
  | 'ur'
  | 'hi-en';

export interface LanguageOption {
  code: LanguageHint;
  label: string;
  nativeLabel: string;
  validated: boolean;
  status: 'validated' | 'experimental';
}

export const LANGUAGE_REGISTRY: LanguageOption[] = [
  { code: 'unknown', label: 'Auto Detect (Hindi-English Mixed)', nativeLabel: 'Auto', validated: true, status: 'validated' },
  { code: 'hi', label: 'Hindi', nativeLabel: 'हिंदी', validated: true, status: 'validated' },
  { code: 'en', label: 'English', nativeLabel: 'English', validated: true, status: 'validated' },
  { code: 'mr', label: 'Marathi', nativeLabel: 'मराठी', validated: false, status: 'experimental' },
  { code: 'bn', label: 'Bengali', nativeLabel: 'বাংলা', validated: false, status: 'experimental' },
  { code: 'ta', label: 'Tamil', nativeLabel: 'தமிழ்', validated: false, status: 'experimental' },
  { code: 'te', label: 'Telugu', nativeLabel: 'తెలుగు', validated: false, status: 'experimental' },
  { code: 'gu', label: 'Gujarati', nativeLabel: 'ગુજરાતી', validated: false, status: 'experimental' },
  { code: 'kn', label: 'Kannada', nativeLabel: 'ಕನ್ನಡ', validated: false, status: 'experimental' },
  { code: 'ml', label: 'Malayalam', nativeLabel: 'മലയാളം', validated: false, status: 'experimental' },
  { code: 'pa', label: 'Punjabi', nativeLabel: 'ਪੰਜਾਬੀ', validated: false, status: 'experimental' },
  { code: 'or', label: 'Odia', nativeLabel: 'ଓଡ଼ିଆ', validated: false, status: 'experimental' },
  { code: 'as', label: 'Assamese', nativeLabel: 'অসমীয়া', validated: false, status: 'experimental' },
  { code: 'ne', label: 'Nepali', nativeLabel: 'नेपाली', validated: false, status: 'experimental' },
  { code: 'sa', label: 'Sanskrit', nativeLabel: 'संस्कृतम्', validated: false, status: 'experimental' },
  { code: 'ur', label: 'Urdu', nativeLabel: 'اردو', validated: false, status: 'experimental' },
];

export type BackendPipelineState =
  | 'AUDIO_RECEIVED'
  | 'STT_PARTIAL'
  | 'STT_FINAL'
  | 'SPECULATIVE_RETRIEVAL'
  | 'RETRIEVED'
  | 'INPUT_GUARDED'
  | 'EVIDENCE_SELECTED'
  | 'ANSWERED'
  | 'VERIFIED'
  | 'COMPLETED'
  | 'ABSTAINED'
  | 'NEEDS_REPEAT'
  | 'UNSAFE'
  | 'DEADLINE_FALLBACK'
  | 'DEPENDENCY_UNAVAILABLE'
  | 'FAILED';

export type PipelineState = BackendPipelineState;

export type UserFacingStatusGroup =
  | 'Transcribing'
  | 'Retrieving evidence'
  | 'Checking the question'
  | 'Selecting evidence'
  | 'Preparing the answer'
  | 'Verifying grounding'
  | 'Completed'
  | 'Not enough evidence'
  | 'Please repeat'
  | 'Request blocked'
  | 'Evidence fallback'
  | 'Service unavailable'
  | 'Failed';

export const PIPELINE_STATE_TO_USER_STATUS: Record<BackendPipelineState, UserFacingStatusGroup> = {
  AUDIO_RECEIVED: 'Transcribing',
  STT_PARTIAL: 'Transcribing',
  STT_FINAL: 'Transcribing',
  SPECULATIVE_RETRIEVAL: 'Retrieving evidence',
  RETRIEVED: 'Retrieving evidence',
  INPUT_GUARDED: 'Checking the question',
  EVIDENCE_SELECTED: 'Selecting evidence',
  ANSWERED: 'Preparing the answer',
  VERIFIED: 'Verifying grounding',
  COMPLETED: 'Completed',
  ABSTAINED: 'Not enough evidence',
  NEEDS_REPEAT: 'Please repeat',
  UNSAFE: 'Request blocked',
  DEADLINE_FALLBACK: 'Evidence fallback',
  DEPENDENCY_UNAVAILABLE: 'Service unavailable',
  FAILED: 'Failed',
};

// ==========================================
// Citations & Terminal Outcomes
// ==========================================

export interface Citation {
  cited_text: string;
  document_id: string;
  parent_id?: string;
  chunk_id: string;
  strategy: string;
  coordinate_system?: string;
  char_start?: number;
  char_end?: number;
  dense_score?: number | null;
  sparse_score?: number | null;
}

export interface GuardrailDecision {
  decision: 'pass' | 'abstain' | 'unsafe' | 'clarify';
  reason?: string;
  user_message?: string;
}

export type AnswerMode =
  | 'grounded_extractive'
  | 'deadline_fallback'
  | 'abstention'
  | 'unsupported';

export interface QueryResponse {
  request_id: string;
  state: BackendPipelineState;
  answer_mode: AnswerMode;
  answer_text?: string | null;
  answer?: string | null;
  abstention_reason?: string | null;
  transcript?: string;
  language?: string;
  citations: Citation[];
  guardrail?: GuardrailDecision;
  agreement_score?: number | null;
  timings?: Record<string, number>;
  timings_ms?: Record<string, number>;
  completed_at?: string;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
    details?: unknown;
  };
}

export type VoiceResultData = QueryResponse;

export type VoiceState =
  | 'idle'
  | 'requesting_permission'
  | 'recording'
  | 'processing'
  | 'terminal';

export type VoiceRecorderState = VoiceState;

export interface VoiceErrorState {
  type: string;
  message: string;
  retryable?: boolean;
  details?: unknown;
}

export type VoiceRecorderError = VoiceErrorState;

// ==========================================
// Text & Voice Request / Event Payloads
// ==========================================

export interface TextQueryRequest {
  query: string;
  language: LanguageHint;
  request_id: string;
  deadline_ms: number | null;
}

export interface VoiceStartFrame {
  type: 'start';
  version: '1';
  request_id: string;
  encoding: 'pcm_s16le';
  sample_rate_hz: 16000;
  language: LanguageHint;
}

export interface VoiceAudioChunkFrame {
  type: 'audio_chunk';
  version: '1';
  sequence: number;
  audio_b64: string;
}

export interface VoiceEndOfStreamFrame {
  type: 'end_of_stream';
  version: '1';
}

export type VoiceClientFrame =
  | VoiceStartFrame
  | VoiceAudioChunkFrame
  | VoiceEndOfStreamFrame;

// Server WebSocket discriminated events
export interface SttPartialEvent {
  type: 'stt_partial';
  transcript?: string;
  language?: string;
  confidence?: number | null;
  payload?: {
    text?: string;
    language?: string;
    confidence?: number | null;
  };
}

export interface PipelineStateEvent {
  type: 'pipeline_state';
  state?: BackendPipelineState;
  payload?: {
    state?: BackendPipelineState;
  };
}

export interface AnswerEvent {
  type: 'answer';
  request_id?: string;
  payload?: QueryResponse;
  answer_mode?: AnswerMode;
  answer_text?: string | null;
  transcript?: string;
  language?: string;
  citations?: Citation[];
  abstention_reason?: string | null;
  guardrail?: GuardrailDecision;
  timings?: Record<string, number>;
}

export interface ErrorEvent {
  type: 'error';
  code?: string;
  state?: BackendPipelineState;
  message?: string;
  retryable?: boolean;
  details?: unknown;
  timings_ms?: Record<string, number>;
  payload?: {
    message?: string;
    code?: string;
    details?: unknown;
  };
}

export type VoiceServerEvent =
  | SttPartialEvent
  | PipelineStateEvent
  | AnswerEvent
  | ErrorEvent;

// ==========================================
// Evidence Summary API (GET /v1/evidence/summary)
// ==========================================

export interface RetrievalMetrics {
  status: 'qualifying' | 'non_qualifying' | 'not_measured';
  qualifying: boolean;
  sample_count: number;
  recall_at_1: number;
  recall_at_5: number;
  recall_at_10: number;
  mrr_at_10: number;
  ndcg_at_10: number;
  retrieval_hit_coverage: number;
  failure_count: number;
  split_verified: boolean;
  direct_p50_ms?: number;
  direct_p70_ms?: number;
  direct_p95_ms?: number;
  direct_max_ms?: number;
  source_artifact_sha256: string;
}

export interface CorpusIndexInfo {
  dataset_id?: string;
  document_count: number;
  indexed_chunks_count: number;
  evaluation_fixture_count: number;
  dense_model: string;
  dense_dim: number;
  dense_distance: string;
  sparse_model: string;
  language: string;
  revision: string;
  qdrant_collection: string;
  index_build_id: string;
  source_artifact_sha256: string;
}

export interface ChunkRepresentation {
  strategy: string;
  name: string;
  description: string;
  chunk_count: number;
  avg_text_length: number;
  artifact_bytes: number;
}

export interface DatasetAuditInfo {
  dataset_id: string;
  revision: string;
  source_split: string;
  target_language: string;
  audited_row_count: number;
  candidate_passage_count: number;
  schema_match: boolean;
  malformed_row_count: number;
  duplicate_query_count: number;
  selected_passage_ratio: number;
  query_type_distribution?: Record<string, number>;
  source_artifact_sha256: string;
  status: 'smoke_audit' | 'certified' | 'invalid';
  qualifying: boolean;
}

export interface CorpusScalingInfo {
  baseline_document_count: number;
  baseline_chunk_count: number;
  scaling_comparison_status: string;
  notes?: string;
  source_artifact_sha256: string;
  status: 'not_measured' | 'measured' | 'invalid';
  qualifying: boolean;
}

export interface GuardrailEvidence {
  sample_count: number;
  observed_correct_count: number;
  failure_count: number;
  passed_categories: string[];
  source_artifact_sha256: string;
  status: 'non_qualifying' | 'qualifying';
  qualifying: boolean;
}

export interface VoiceLatencyReport {
  sample_count: number;
  qualifying: boolean;
  status: 'not_measured' | 'measured' | 'invalid';
  cold_p50_ms?: number | null;
  cold_p70_ms?: number | null;
  cold_p95_ms?: number | null;
  cold_p100_ms?: number | null;
  warm_p50_ms?: number | null;
  warm_p70_ms?: number | null;
  warm_p95_ms?: number | null;
  warm_p100_ms?: number | null;
  pending_criteria?: string[];
  source_artifact_sha256?: string;
}

export interface ProvenanceDetails {
  evaluation_split: string;
  code_revision: string;
  manifest_verified: boolean;
  audit_trail_valid: boolean;
  limitations: string[];
}

export type ProvenanceInfo = ProvenanceDetails;

export interface EvidenceSummary {
  schema_version: string;
  generated_at: string;
  retrieval: RetrievalMetrics;
  corpus: CorpusIndexInfo;
  chunk_representations: ChunkRepresentation[];
  dataset_audit: DatasetAuditInfo;
  corpus_scaling: CorpusScalingInfo;
  guardrails: GuardrailEvidence;
  voice_latency: VoiceLatencyReport;
  provenance: ProvenanceDetails;
}
