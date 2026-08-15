export const BACKEND_LANGUAGES = [
  'unknown',
  'as',
  'bn',
  'gu',
  'hi',
  'en',
  'kn',
  'ml',
  'mr',
  'ne',
  'or',
  'pa',
  'sa',
  'ta',
  'te',
  'ur',
  'hi-en',
] as const;

export type ServerLanguageCode = (typeof BACKEND_LANGUAGES)[number];
export type LanguageHint = ServerLanguageCode | 'auto';
export type Language = LanguageHint;

export function toBackendLanguage(language: LanguageHint): ServerLanguageCode {
  return language === 'auto' ? 'unknown' : language;
}

export interface LanguageOption {
  code: LanguageHint;
  label: string;
  nativeLabel: string;
  validated: boolean;
  status: 'validated' | 'experimental';
}

export const LANGUAGE_REGISTRY: LanguageOption[] = [
  { code: 'auto', label: 'Auto detect', nativeLabel: 'Auto', validated: true, status: 'validated' },
  { code: 'hi', label: 'Hindi', nativeLabel: 'हिंदी', validated: true, status: 'validated' },
  { code: 'hi-en', label: 'Hinglish', nativeLabel: 'Hinglish', validated: true, status: 'validated' },
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

export function getLanguageDisplayLabel(language: string): string {
  return LANGUAGE_REGISTRY.find((option) => option.code === language)?.label ?? language.toUpperCase();
}

export const PIPELINE_STATES = [
  'AUDIO_RECEIVED',
  'STT_PARTIAL',
  'SPECULATIVE_RETRIEVAL',
  'STT_FINAL',
  'INPUT_GUARDED',
  'RETRIEVED',
  'EVIDENCE_SELECTED',
  'ANSWERED',
  'VERIFIED',
  'COMPLETED',
  'ABSTAINED',
  'NEEDS_REPEAT',
  'UNSAFE',
  'DEADLINE_FALLBACK',
  'DEPENDENCY_UNAVAILABLE',
  'FAILED',
] as const;

export type BackendPipelineState = (typeof PIPELINE_STATES)[number];
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
  | 'Deadline fallback'
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
  DEADLINE_FALLBACK: 'Deadline fallback',
  DEPENDENCY_UNAVAILABLE: 'Service unavailable',
  FAILED: 'Failed',
};

export interface HealthResponse {
  status: 'healthy' | 'offline' | 'unhealthy';
  version: string | null;
  error?: string;
}

export interface ReadyCheck {
  ready: boolean;
  reason?: string | null;
  [key: string]: unknown;
}

export interface RuntimeReadiness {
  process_instance_id: string | null;
  process_started_at: string | null;
  voice_requests_started: number | null;
  rag_deadline_ms: number | null;
  rag_fallback_at_ms: number | null;
}

export interface ReadyResponse {
  status: 'ready' | 'not_ready';
  checks: Record<string, ReadyCheck>;
  runtime: RuntimeReadiness;
}

export type GuardrailDecision = 'ALLOW' | 'ABSTAIN' | 'NEEDS_REPEAT' | 'BLOCK' | 'WARN';

export interface GuardrailResult {
  decision: GuardrailDecision;
  reason: string | null;
  evidence: Record<string, unknown>;
  user_message: string | null;
}

export type AnswerMode = 'extractive' | 'llama' | 'evidence_fallback' | 'abstention';

export interface Citation {
  canonical_doc_id: string;
  parent_id: string;
  chunk_id: string;
  strategy: string;
  text: string;
  span_start: number;
  span_end: number;
  span_coordinate_system: 'parent_text' | 'chunk_text' | 'paired_representation';
  source_text_sha256: string;
  dense_score: number | null;
  sparse_score: number | null;
}

export interface SynthesisOffer {
  token: string;
  provider: 'groq';
  model: 'openai/gpt-oss-20b';
  expires_in_ms: number;
}

export type SynthesisStatus =
  | 'completed'
  | 'abstained'
  | 'timed_out'
  | 'unavailable'
  | 'grounding_failed';

export interface SynthesisClaim {
  text: string;
  citation_indices: number[];
}

export interface SynthesisResponse {
  request_id: string;
  provider: 'groq';
  model: 'openai/gpt-oss-20b';
  status: SynthesisStatus;
  answer: string | null;
  claims: SynthesisClaim[];
  citations: Citation[];
  guardrail: GuardrailResult;
  retryable: false;
  timings_ms: Record<string, number>;
  completed_at: string;
}

export interface SynthesisRequest {
  request_id: string;
  token: string;
}

export interface QueryResponse {
  request_id: string;
  transcript: string;
  language: ServerLanguageCode;
  answer: string | null;
  answer_mode: AnswerMode;
  citations: Citation[];
  guardrail: GuardrailResult;
  evidence_agreement: number | null;
  state: BackendPipelineState;
  timings_ms: Record<string, number>;
  completed_at: string;
  synthesis?: SynthesisOffer | null;
}

export interface PipelineErrorResponse {
  request_id: string;
  code: string;
  state: BackendPipelineState;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
}

export type VoiceResultData = QueryResponse;

export type VoiceState = 'idle' | 'requesting_permission' | 'recording' | 'processing' | 'terminal';
export type VoiceRecorderState = VoiceState;

export interface VoiceErrorState {
  type: string;
  message: string;
  code?: string;
  state?: BackendPipelineState;
  retryable?: boolean;
  details?: Record<string, unknown>;
  timingsMs?: Record<string, number>;
}

export type VoiceRecorderError = VoiceErrorState;

export interface TextQueryRequest {
  query: string;
  language: ServerLanguageCode;
  request_id: string;
  deadline_ms: number | null;
}

export const VERIFIED_PROMPT_LANGUAGES = ['hi', 'en', 'hi-en'] as const;
export type VerifiedPromptLanguage = (typeof VERIFIED_PROMPT_LANGUAGES)[number];

export const VERIFIED_PROMPT_CONDITIONS = [
  'clean-short',
  'clean-long',
  'noisy-short',
  'noisy-long',
] as const;
export type VerifiedPromptCondition = (typeof VERIFIED_PROMPT_CONDITIONS)[number];
export type VerifiedPromptLength = 'short' | 'long';

export interface VerifiedPrompt {
  id: string;
  text: string;
  language: VerifiedPromptLanguage;
  condition: VerifiedPromptCondition;
  length_class: VerifiedPromptLength;
  source_query_id: string;
}

export interface VerifiedPromptCatalog {
  schema_version: '1.0.0';
  catalog_id: 'msmarco-xi-human-voice-v1';
  status: 'recording_plan';
  total: number;
  live_text_validated_count: number;
  coverage: {
    languages: Record<VerifiedPromptLanguage, number>;
    conditions: Record<VerifiedPromptCondition, number>;
    lengths: Record<VerifiedPromptLength, number>;
    source_types: { human: number };
  };
  prompts: VerifiedPrompt[];
}

export interface VoiceStartFrame {
  type: 'start';
  version: '1';
  request_id: string;
  encoding: 'pcm_s16le';
  sample_rate_hz: 16000;
  language: ServerLanguageCode;
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

export type VoiceClientFrame = VoiceStartFrame | VoiceAudioChunkFrame | VoiceEndOfStreamFrame;

export interface SttPartialEvent {
  type: 'stt_partial';
  version: '1';
  request_id: string;
  payload: { text: string; language: ServerLanguageCode; confidence: number | null };
}

export interface PipelineStateEvent {
  type: 'pipeline_state';
  version: '1';
  request_id: string;
  payload: { state: BackendPipelineState };
}

export interface AnswerEvent {
  type: 'answer';
  version: '1';
  request_id: string;
  payload: QueryResponse;
}

export interface ErrorEvent {
  type: 'error';
  version: '1';
  request_id: string;
  payload: {
    code: string;
    state: BackendPipelineState;
    message: string;
    retryable: boolean;
    details: Record<string, unknown>;
    timings_ms: Record<string, number>;
  };
}

export type VoiceServerEvent = SttPartialEvent | PipelineStateEvent | AnswerEvent | ErrorEvent;

export type EvidenceStatus =
  | 'qualifying'
  | 'non_qualifying'
  | 'not_measured'
  | 'invalid'
  | 'partial'
  | 'smoke_audit';

export interface RetrievalMetrics {
  status: EvidenceStatus;
  qualifying: boolean;
  sample_count: number;
  failure_count: number;
  completion_coverage: number | null;
  recall_at_1: number | null;
  recall_at_5: number | null;
  recall_at_10: number | null;
  mrr_at_10: number | null;
  ndcg_at_10: number | null;
  retrieval_hit_coverage: number | null;
  split_verified: boolean;
  direct_latency_sample_count: number | null;
  direct_mean_ms: number | null;
  direct_p50_ms: number | null;
  direct_p70_ms: number | null;
  direct_p95_ms: number | null;
  direct_max_ms: number | null;
  source_artifact_sha256: string | null;
  failed_checks: string[];
}

export interface CorpusIndexInfo {
  status: EvidenceStatus;
  verified: boolean;
  dataset_id: string | null;
  source_split: string | null;
  language: string | null;
  revision: string | null;
  document_count: number | null;
  evaluation_fixture_count: number | null;
  indexed_chunks_count: number | null;
  dense_model: string | null;
  dense_model_revision: string | null;
  dense_dim: number | null;
  dense_distance: string | null;
  sparse_model: string | null;
  qdrant_collection: string | null;
  index_build_id: string | null;
  source_artifact_sha256: string | null;
  index_manifest_sha256: string | null;
  failed_checks: string[];
}

export interface ChunkRepresentation {
  strategy: string;
  name: string;
  description: string;
  enabled: boolean;
  chunk_count: number;
  avg_text_length: number;
  artifact_bytes: number;
  build_duration_seconds: number;
}

export interface DatasetAuditInfo {
  status: EvidenceStatus;
  qualifying: boolean;
  dataset_id: string | null;
  revision: string | null;
  source_split: string | null;
  target_language: string | null;
  audited_row_count: number;
  candidate_passage_count: number;
  schema_match: boolean | null;
  malformed_row_count: number;
  duplicate_query_count: number;
  selected_passage_ratio: number | null;
  query_type_distribution: Record<string, number>;
  source_artifact_sha256: string | null;
  failed_checks: string[];
}

export interface CorpusScalingInfo {
  status: EvidenceStatus;
  qualifying: boolean;
  baseline_document_count: number | null;
  baseline_chunk_count: number | null;
  scaling_comparison_status: string;
  notes: string | null;
  source_artifact_sha256: string | null;
  failed_checks: string[];
}

export interface GuardrailEvidence {
  status: EvidenceStatus;
  qualifying: boolean;
  sample_count: number;
  observed_correct_count: number;
  failure_count: number;
  passed_categories: string[];
  failed_checks: string[];
  source_artifact_sha256: string | null;
}

export interface VoiceLatencyReport {
  status: EvidenceStatus;
  qualifying: boolean;
  sample_count: number;
  cold_p50_ms: number | null;
  cold_p70_ms: number | null;
  cold_p95_ms: number | null;
  cold_p100_ms: number | null;
  warm_p50_ms: number | null;
  warm_p70_ms: number | null;
  warm_p95_ms: number | null;
  warm_p100_ms: number | null;
  pending_criteria: string[];
  failed_checks: string[];
  source_artifact_sha256: string | null;
}

export interface LatencyPercentiles {
  p50: number;
  p70: number;
  p95: number;
  p100: number;
}

export interface StageLatencyPercentiles extends LatencyPercentiles {
  count: number;
}

export interface OperationalMetrics {
  requests_total: number;
  latency_sample_count: number;
  latency_ms: LatencyPercentiles | null;
  timings_ms: Record<string, StageLatencyPercentiles>;
  groq_synthesis: {
    latency_sample_count: number;
    latency_ms: LatencyPercentiles | null;
  };
}

export interface ProvenanceDetails {
  evaluation_split: string | null;
  manifest_verified: boolean;
  audit_trail_valid: boolean;
  artifact_hashes: Record<string, string>;
  limitations: string[];
}

export type ProvenanceInfo = ProvenanceDetails;

export interface EvidenceSummary {
  schema_version: '2.0.0';
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return isNumber(value) && Number.isInteger(value) && value >= 0;
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean';
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || isNumber(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isLanguage(value: unknown): value is ServerLanguageCode {
  return isString(value) && (BACKEND_LANGUAGES as readonly string[]).includes(value);
}

function isPipelineState(value: unknown): value is BackendPipelineState {
  return isString(value) && (PIPELINE_STATES as readonly string[]).includes(value);
}

const EVIDENCE_STATUSES: readonly EvidenceStatus[] = [
  'qualifying', 'non_qualifying', 'not_measured', 'invalid', 'partial', 'smoke_audit',
];

function isEvidenceStatus(value: unknown): value is EvidenceStatus {
  return isString(value) && EVIDENCE_STATUSES.includes(value as EvidenceStatus);
}

function assertProtocol(condition: boolean, message: string): asserts condition {
  if (!condition) throw new Error(`Protocol error: ${message}`);
}

function parseNumberMap(value: unknown, field: string): Record<string, number> {
  assertProtocol(isRecord(value), `${field} must be an object`);
  const output: Record<string, number> = {};
  for (const [key, item] of Object.entries(value)) {
    assertProtocol(isNumber(item), `${field}.${key} must be a finite number`);
    output[key] = item;
  }
  return output;
}

function parseCitation(value: unknown): Citation {
  assertProtocol(isRecord(value), 'citation must be an object');
  assertProtocol(isString(value.canonical_doc_id), 'citation.canonical_doc_id is required');
  assertProtocol(isString(value.parent_id), 'citation.parent_id is required');
  assertProtocol(isString(value.chunk_id), 'citation.chunk_id is required');
  assertProtocol(isString(value.strategy), 'citation.strategy is required');
  assertProtocol(isString(value.text), 'citation.text is required');
  assertProtocol(isNumber(value.span_start), 'citation.span_start is required');
  assertProtocol(isNumber(value.span_end), 'citation.span_end is required');
  assertProtocol(
    value.span_coordinate_system === 'parent_text' ||
      value.span_coordinate_system === 'chunk_text' ||
      value.span_coordinate_system === 'paired_representation',
    'citation.span_coordinate_system is invalid'
  );
  assertProtocol(isString(value.source_text_sha256), 'citation.source_text_sha256 is required');
  assertProtocol(isNullableNumber(value.dense_score), 'citation.dense_score is invalid');
  assertProtocol(isNullableNumber(value.sparse_score), 'citation.sparse_score is invalid');
  return value as unknown as Citation;
}

function parseSynthesisOffer(value: unknown): SynthesisOffer {
  assertProtocol(isRecord(value), 'synthesis must be an object or null');
  assertProtocol(
    isString(value.token) &&
      value.token.length >= 32 &&
      value.token.length <= 128 &&
      /^[A-Za-z0-9_-]+$/.test(value.token),
    'synthesis.token is invalid'
  );
  assertProtocol(value.provider === 'groq', 'synthesis.provider is invalid');
  assertProtocol(value.model === 'openai/gpt-oss-20b', 'synthesis.model is invalid');
  assertProtocol(
    isNumber(value.expires_in_ms) &&
      Number.isInteger(value.expires_in_ms) &&
      value.expires_in_ms > 0 &&
      value.expires_in_ms <= 600_000,
    'synthesis.expires_in_ms must be a positive bounded integer'
  );
  return value as unknown as SynthesisOffer;
}

function parseSynthesisClaim(value: unknown, citationCount: number): SynthesisClaim {
  assertProtocol(isRecord(value), 'synthesis claim must be an object');
  assertProtocol(isString(value.text) && value.text.trim().length > 0, 'synthesis claim text is required');
  assertProtocol(
    Array.isArray(value.citation_indices),
    'synthesis claim citation_indices must be an array'
  );
  const citationIndices = value.citation_indices.map((item) => {
    assertProtocol(
      isNumber(item) && Number.isInteger(item) && item >= 0 && item < citationCount,
      'synthesis claim citation index is invalid'
    );
    return item;
  });
  assertProtocol(
    citationIndices.length > 0 && citationIndices.length <= 3,
    'synthesis claim must cite between one and three evidence spans'
  );
  assertProtocol(
    new Set(citationIndices).size === citationIndices.length,
    'synthesis claim citation indices must be unique'
  );
  return { text: value.text.trim(), citation_indices: citationIndices };
}

function parseGuardrail(value: unknown): GuardrailResult {
  assertProtocol(isRecord(value), 'guardrail must be an object');
  assertProtocol(
    value.decision === 'ALLOW' ||
      value.decision === 'ABSTAIN' ||
      value.decision === 'NEEDS_REPEAT' ||
      value.decision === 'BLOCK' ||
      value.decision === 'WARN',
    'guardrail.decision is invalid'
  );
  assertProtocol(value.reason === null || isString(value.reason), 'guardrail.reason is invalid');
  assertProtocol(isRecord(value.evidence), 'guardrail.evidence must be an object');
  assertProtocol(
    value.user_message === null || isString(value.user_message),
    'guardrail.user_message is invalid'
  );
  return value as unknown as GuardrailResult;
}

function parseCoverageCounts<const T extends readonly string[]>(
  value: unknown,
  field: string,
  expectedKeys: T,
): Record<T[number], number> {
  assertProtocol(isRecord(value), `${field} must be an object`);
  const actualKeys = Object.keys(value).sort();
  const requiredKeys = [...expectedKeys].sort();
  assertProtocol(
    actualKeys.length === requiredKeys.length &&
      actualKeys.every((key, index) => key === requiredKeys[index]),
    `${field} must contain exactly ${requiredKeys.join(', ')}`,
  );
  for (const key of expectedKeys) {
    assertProtocol(isNonNegativeInteger(value[key]), `${field}.${key} must be a non-negative integer`);
  }
  return value as Record<T[number], number>;
}

export function parseVerifiedPromptCatalog(value: unknown): VerifiedPromptCatalog {
  assertProtocol(isRecord(value), 'verified prompt catalog must be an object');
  assertProtocol(value.schema_version === '1.0.0', 'unsupported verified prompt schema version');
  assertProtocol(
    value.catalog_id === 'msmarco-xi-human-voice-v1',
    'verified prompt catalog_id is invalid',
  );
  assertProtocol(value.status === 'recording_plan', 'verified prompt status is invalid');
  assertProtocol(isNonNegativeInteger(value.total), 'verified prompt total is invalid');
  assertProtocol(
    isNonNegativeInteger(value.live_text_validated_count),
    'verified prompt live_text_validated_count is invalid',
  );
  assertProtocol(Array.isArray(value.prompts), 'verified prompts must be an array');
  assertProtocol(value.prompts.length === value.total, 'verified prompt total does not match prompts');
  assertProtocol(
    value.live_text_validated_count <= value.total,
    'verified prompt validated count exceeds total',
  );

  const seenIds = new Set<string>();
  const prompts = value.prompts.map((prompt, index): VerifiedPrompt => {
    assertProtocol(isRecord(prompt), `verified prompts.${index} must be an object`);
    assertProtocol(isString(prompt.id) && prompt.id.trim().length > 0, `verified prompts.${index}.id is required`);
    assertProtocol(!seenIds.has(prompt.id), `verified prompts.${index}.id must be unique`);
    seenIds.add(prompt.id);
    assertProtocol(
      isString(prompt.text) && prompt.text.trim().length > 0,
      `verified prompts.${index}.text is required`,
    );
    assertProtocol(
      isString(prompt.language) &&
        (VERIFIED_PROMPT_LANGUAGES as readonly string[]).includes(prompt.language),
      `verified prompts.${index}.language is invalid`,
    );
    assertProtocol(
      isString(prompt.condition) &&
        (VERIFIED_PROMPT_CONDITIONS as readonly string[]).includes(prompt.condition),
      `verified prompts.${index}.condition is invalid`,
    );
    assertProtocol(
      prompt.length_class === 'short' || prompt.length_class === 'long',
      `verified prompts.${index}.length_class is invalid`,
    );
    assertProtocol(
      prompt.condition.endsWith(prompt.length_class),
      `verified prompts.${index} condition and length_class disagree`,
    );
    assertProtocol(
      isString(prompt.source_query_id) && prompt.source_query_id.trim().length > 0,
      `verified prompts.${index}.source_query_id is required`,
    );
    return prompt as unknown as VerifiedPrompt;
  });

  assertProtocol(isRecord(value.coverage), 'verified prompt coverage must be an object');
  const languages = parseCoverageCounts(
    value.coverage.languages,
    'verified prompt coverage.languages',
    VERIFIED_PROMPT_LANGUAGES,
  );
  const conditions = parseCoverageCounts(
    value.coverage.conditions,
    'verified prompt coverage.conditions',
    VERIFIED_PROMPT_CONDITIONS,
  );
  const lengths = parseCoverageCounts(
    value.coverage.lengths,
    'verified prompt coverage.lengths',
    ['short', 'long'] as const,
  );
  const sourceTypes = parseCoverageCounts(
    value.coverage.source_types,
    'verified prompt coverage.source_types',
    ['human'] as const,
  );
  for (const [field, counts] of [
    ['languages', languages],
    ['conditions', conditions],
    ['lengths', lengths],
    ['source_types', sourceTypes],
  ] as const) {
    assertProtocol(
      Object.values(counts).reduce((sum, count) => sum + count, 0) === value.total,
      `verified prompt coverage.${field} does not match total`,
    );
  }

  return {
    schema_version: '1.0.0',
    catalog_id: 'msmarco-xi-human-voice-v1',
    status: 'recording_plan',
    total: value.total,
    live_text_validated_count: value.live_text_validated_count,
    coverage: { languages, conditions, lengths, source_types: sourceTypes },
    prompts,
  };
}

export function parseQueryResponse(value: unknown): QueryResponse {
  assertProtocol(isRecord(value), 'query response must be an object');
  assertProtocol(isString(value.request_id), 'request_id is required');
  assertProtocol(isString(value.transcript), 'transcript is required');
  assertProtocol(isLanguage(value.language), 'language is invalid');
  assertProtocol(value.answer === null || isString(value.answer), 'answer is invalid');
  assertProtocol(
    value.answer_mode === 'extractive' ||
      value.answer_mode === 'llama' ||
      value.answer_mode === 'evidence_fallback' ||
      value.answer_mode === 'abstention',
    'answer_mode is invalid'
  );
  assertProtocol(Array.isArray(value.citations), 'citations must be an array');
  const citations = value.citations.map(parseCitation);
  const guardrail = parseGuardrail(value.guardrail);
  assertProtocol(
    value.evidence_agreement === null || isNumber(value.evidence_agreement),
    'evidence_agreement is invalid'
  );
  assertProtocol(isPipelineState(value.state), 'state is invalid');
  const timings = parseNumberMap(value.timings_ms, 'timings_ms');
  assertProtocol(isString(value.completed_at), 'completed_at is required');
  const synthesis = value.synthesis === undefined || value.synthesis === null
    ? value.synthesis
    : parseSynthesisOffer(value.synthesis);
  return {
    ...(value as unknown as QueryResponse),
    citations,
    guardrail,
    timings_ms: timings,
    synthesis,
  };
}

export function parseSynthesisResponse(value: unknown): SynthesisResponse {
  assertProtocol(isRecord(value), 'synthesis response must be an object');
  assertProtocol(
    isString(value.request_id) && value.request_id.length > 0 && value.request_id.length <= 128,
    'synthesis request_id is invalid'
  );
  assertProtocol(value.provider === 'groq', 'synthesis provider is invalid');
  assertProtocol(value.model === 'openai/gpt-oss-20b', 'synthesis model is invalid');
  assertProtocol(
    value.status === 'completed' ||
      value.status === 'abstained' ||
      value.status === 'timed_out' ||
      value.status === 'unavailable' ||
      value.status === 'grounding_failed',
    'synthesis status is invalid'
  );
  assertProtocol(value.answer === null || isString(value.answer), 'synthesis answer is invalid');
  assertProtocol(Array.isArray(value.citations), 'synthesis citations must be an array');
  const citations = value.citations.map(parseCitation);
  assertProtocol(Array.isArray(value.claims), 'synthesis claims must be an array');
  assertProtocol(value.claims.length <= 3, 'synthesis claims must contain at most three items');
  const claims = value.claims.map((claim) => parseSynthesisClaim(claim, citations.length));
  assertProtocol(citations.length <= 3, 'synthesis citations must contain at most three items');
  const guardrail = parseGuardrail(value.guardrail);
  assertProtocol(isBoolean(value.retryable), 'synthesis retryable is required');
  assertProtocol(value.retryable === false, 'synthesis offers cannot be retried');
  const timings = parseNumberMap(value.timings_ms, 'synthesis timings_ms');
  assertProtocol(isString(value.completed_at), 'synthesis completed_at is required');
  if (value.status === 'completed') {
    assertProtocol(
      isString(value.answer) && value.answer.trim().length > 0,
      'completed synthesis answer is required'
    );
    assertProtocol(claims.length > 0, 'completed synthesis claims are required');
    assertProtocol(citations.length > 0, 'completed synthesis citations are required');
    assertProtocol(guardrail.decision === 'ALLOW', 'completed synthesis must pass its guardrail');
    const normalizedAnswer = value.answer.split(/\s+/u).filter(Boolean).join(' ');
    const normalizedClaims = claims
      .map((claim) => claim.text.trim())
      .join(' ')
      .split(/\s+/u)
      .filter(Boolean)
      .join(' ');
    assertProtocol(normalizedAnswer === normalizedClaims, 'completed synthesis answer must equal its ordered claim texts');
  } else {
    assertProtocol(value.answer === null, 'non-completed synthesis answer must be null');
    assertProtocol(claims.length === 0, 'non-completed synthesis claims must be empty');
    assertProtocol(citations.length === 0, 'non-completed synthesis citations must be empty');
  }
  return {
    ...(value as unknown as SynthesisResponse),
    citations,
    claims,
    guardrail,
    timings_ms: timings,
  };
}

export function parsePipelineError(value: unknown): PipelineErrorResponse {
  assertProtocol(isRecord(value), 'error response must be an object');
  assertProtocol(isString(value.request_id), 'error.request_id is required');
  assertProtocol(isString(value.code), 'error.code is required');
  assertProtocol(isPipelineState(value.state), 'error.state is invalid');
  assertProtocol(isString(value.message), 'error.message is required');
  assertProtocol(isBoolean(value.retryable), 'error.retryable is required');
  assertProtocol(isRecord(value.details), 'error.details must be an object');
  return value as unknown as PipelineErrorResponse;
}

export function parseVoiceServerEvent(value: unknown): VoiceServerEvent {
  assertProtocol(isRecord(value), 'server event must be an object');
  assertProtocol(value.version === '1', 'unsupported server event version');
  assertProtocol(isString(value.request_id), 'server event request_id is required');
  assertProtocol(isRecord(value.payload), 'server event payload must be an object');
  if (value.type === 'stt_partial') {
    assertProtocol(isString(value.payload.text), 'partial text is required');
    assertProtocol(isLanguage(value.payload.language), 'partial language is invalid');
    assertProtocol(isNullableNumber(value.payload.confidence), 'partial confidence is invalid');
    return value as unknown as SttPartialEvent;
  }
  if (value.type === 'pipeline_state') {
    assertProtocol(isPipelineState(value.payload.state), 'pipeline state is invalid');
    return value as unknown as PipelineStateEvent;
  }
  if (value.type === 'answer') {
    return { ...value, payload: parseQueryResponse(value.payload) } as AnswerEvent;
  }
  if (value.type === 'error') {
    assertProtocol(isString(value.payload.code), 'voice error code is required');
    assertProtocol(isPipelineState(value.payload.state), 'voice error state is invalid');
    assertProtocol(isString(value.payload.message), 'voice error message is required');
    assertProtocol(isBoolean(value.payload.retryable), 'voice error retryable is required');
    assertProtocol(isRecord(value.payload.details), 'voice error details are invalid');
    parseNumberMap(value.payload.timings_ms, 'voice error timings_ms');
    return value as unknown as ErrorEvent;
  }
  throw new Error('Protocol error: unsupported server event type');
}

export function parseHealthResponse(value: unknown): HealthResponse {
  assertProtocol(isRecord(value), 'health response must be an object');
  assertProtocol(value.status === 'healthy', 'health status is invalid');
  assertProtocol(isString(value.version), 'health version is required');
  return { status: 'healthy', version: value.version };
}

export function parseReadyResponse(value: unknown): ReadyResponse {
  assertProtocol(isRecord(value), 'ready response must be an object');
  assertProtocol(value.status === 'ready' || value.status === 'not_ready', 'ready status is invalid');
  assertProtocol(isRecord(value.checks), 'ready checks must be an object');
  const checks: Record<string, ReadyCheck> = {};
  for (const [name, check] of Object.entries(value.checks)) {
    assertProtocol(isRecord(check) && isBoolean(check.ready), `ready check ${name} is invalid`);
    checks[name] = check as ReadyCheck;
  }
  assertProtocol(isRecord(value.runtime), 'ready runtime must be an object');
  for (const field of ['process_instance_id', 'process_started_at'] as const) {
    assertProtocol(value.runtime[field] === null || isString(value.runtime[field]), `ready runtime ${field} is invalid`);
  }
  for (const field of ['voice_requests_started', 'rag_deadline_ms', 'rag_fallback_at_ms'] as const) {
    assertProtocol(value.runtime[field] === null || isNumber(value.runtime[field]), `ready runtime ${field} is invalid`);
  }
  return { ...(value as unknown as ReadyResponse), checks };
}

function validateEvidenceGroup(value: unknown, name: string): asserts value is Record<string, unknown> {
  assertProtocol(isRecord(value), `${name} must be an object`);
  assertProtocol(isEvidenceStatus(value.status), `${name}.status is invalid`);
  assertProtocol(isBoolean(value.qualifying), `${name}.qualifying is required`);
}

export function parseEvidenceSummary(value: unknown): EvidenceSummary {
  assertProtocol(isRecord(value), 'evidence summary must be an object');
  assertProtocol(value.schema_version === '2.0.0', 'unsupported evidence schema version');
  assertProtocol(isString(value.generated_at), 'evidence generated_at is required');
  validateEvidenceGroup(value.retrieval, 'retrieval');
  assertProtocol(isNumber(value.retrieval.sample_count), 'retrieval.sample_count is invalid');
  assertProtocol(isRecord(value.corpus), 'corpus must be an object');
  assertProtocol(isEvidenceStatus(value.corpus.status), 'corpus.status is invalid');
  assertProtocol(isBoolean(value.corpus.verified), 'corpus.verified is invalid');
  assertProtocol(Array.isArray(value.chunk_representations), 'chunk_representations must be an array');
  for (const representation of value.chunk_representations) {
    assertProtocol(isRecord(representation), 'chunk representation is invalid');
    assertProtocol(isString(representation.strategy), 'chunk strategy is required');
    assertProtocol(isNumber(representation.chunk_count), 'chunk count is invalid');
  }
  validateEvidenceGroup(value.dataset_audit, 'dataset_audit');
  validateEvidenceGroup(value.corpus_scaling, 'corpus_scaling');
  validateEvidenceGroup(value.guardrails, 'guardrails');
  validateEvidenceGroup(value.voice_latency, 'voice_latency');
  assertProtocol(isRecord(value.provenance), 'provenance must be an object');
  assertProtocol(isBoolean(value.provenance.manifest_verified), 'provenance manifest state is invalid');
  assertProtocol(isBoolean(value.provenance.audit_trail_valid), 'provenance audit state is invalid');
  assertProtocol(isStringArray(value.provenance.limitations), 'provenance limitations are invalid');
  return value as unknown as EvidenceSummary;
}

function parseLatencyPercentiles(value: unknown, field: string): LatencyPercentiles | null {
  if (value === undefined || value === null) return null;
  assertProtocol(isRecord(value), `${field} must be an object`);
  for (const percentile of ['p50', 'p70', 'p95', 'p100'] as const) {
    assertProtocol(
      isNumber(value[percentile]) && value[percentile] >= 0,
      `${field}.${percentile} must be a non-negative finite number`,
    );
  }
  return value as unknown as LatencyPercentiles;
}

export function parseOperationalMetrics(value: unknown): OperationalMetrics {
  assertProtocol(isRecord(value), 'operational metrics must be an object');
  assertProtocol(
    isNumber(value.requests_total) && Number.isInteger(value.requests_total) && value.requests_total >= 0,
    'operational metrics requests_total is invalid',
  );
  assertProtocol(
    isNumber(value.latency_sample_count) &&
      Number.isInteger(value.latency_sample_count) &&
      value.latency_sample_count >= 0,
    'operational metrics latency_sample_count is invalid',
  );
  const latency = parseLatencyPercentiles(value.latency_ms, 'operational metrics latency_ms');
  assertProtocol(isRecord(value.timings_ms), 'operational metrics timings_ms must be an object');
  const timings: Record<string, StageLatencyPercentiles> = {};
  for (const [name, item] of Object.entries(value.timings_ms)) {
    assertProtocol(isRecord(item), `operational metrics timings_ms.${name} must be an object`);
    assertProtocol(
      isNumber(item.count) && Number.isInteger(item.count) && item.count >= 0,
      `operational metrics timings_ms.${name}.count is invalid`,
    );
    const percentiles = parseLatencyPercentiles(
      item,
      `operational metrics timings_ms.${name}`,
    );
    assertProtocol(percentiles !== null, `operational metrics timings_ms.${name} is invalid`);
    timings[name] = { count: item.count, ...percentiles };
  }
  assertProtocol(isRecord(value.groq_synthesis), 'operational metrics groq_synthesis must be an object');
  assertProtocol(
    isNumber(value.groq_synthesis.latency_sample_count) &&
      Number.isInteger(value.groq_synthesis.latency_sample_count) &&
      value.groq_synthesis.latency_sample_count >= 0,
    'operational metrics groq_synthesis.latency_sample_count is invalid',
  );
  return {
    requests_total: value.requests_total,
    latency_sample_count: value.latency_sample_count,
    latency_ms: latency,
    timings_ms: timings,
    groq_synthesis: {
      latency_sample_count: value.groq_synthesis.latency_sample_count,
      latency_ms: parseLatencyPercentiles(
        value.groq_synthesis.latency_ms,
        'operational metrics groq_synthesis.latency_ms',
      ),
    },
  };
}
