import { describe, expect, it } from 'vitest';
import { getLanguageDisplayLabel, LANGUAGE_REGISTRY, parseEvidenceSummary, parseQueryResponse, parseReadyResponse, parseVoiceServerEvent, toBackendLanguage } from './api';

const queryResponse = {
  request_id: 'request-1',
  transcript: 'What is influenza?',
  language: 'en',
  answer: 'Influenza is a viral respiratory illness.',
  answer_mode: 'extractive',
  citations: [{
    canonical_doc_id: 'doc-1', parent_id: 'parent-1', chunk_id: 'chunk-1', strategy: 'atomic',
    text: 'Influenza is a viral respiratory illness.', span_start: 0, span_end: 41,
    span_coordinate_system: 'parent_text', source_text_sha256: 'a'.repeat(64), dense_score: 0.8,
    sparse_score: null,
  }],
  guardrail: { decision: 'ALLOW', reason: null, evidence: {}, user_message: null },
  evidence_agreement: 1,
  state: 'COMPLETED',
  timings_ms: { total_duration_ms: 120 },
  completed_at: '2026-08-15T00:00:00Z',
};

describe('frontend/backend protocol', () => {
  it('maps auto to the backend unknown enum', () => expect(toBackendLanguage('auto')).toBe('unknown'));

  it('sends the explicit Hinglish selection as the backend code-mixed language', () => {
    expect(toBackendLanguage('hi-en')).toBe('hi-en');
  });

  it('exposes Hinglish as a validated language and renders a readable label', () => {
    expect(LANGUAGE_REGISTRY).toContainEqual({
      code: 'hi-en',
      label: 'Hinglish',
      nativeLabel: 'Hinglish',
      validated: true,
      status: 'validated',
    });
    expect(getLanguageDisplayLabel('hi-en')).toBe('Hinglish');
  });

  it('accepts code-mixed language values returned by the backend', () => {
    expect(parseQueryResponse({ ...queryResponse, language: 'hi-en' }).language).toBe('hi-en');
    const event = parseVoiceServerEvent({
      type: 'stt_partial',
      version: '1',
      request_id: 'request-1',
      payload: { text: 'भारत में allocation क्या है?', language: 'hi-en', confidence: null },
    });
    expect(event.type).toBe('stt_partial');
    if (event.type === 'stt_partial') expect(event.payload.language).toBe('hi-en');
  });

  it('accepts the exact query response and rejects legacy answer_text', () => {
    expect(parseQueryResponse(queryResponse).answer).toContain('viral');
    expect(() => parseQueryResponse({ ...queryResponse, answer: undefined, answer_text: 'legacy' })).toThrow();
  });

  it('preserves terminal websocket payload state', () => {
    const event = parseVoiceServerEvent({ type: 'answer', version: '1', request_id: 'request-1', payload: queryResponse });
    expect(event.type).toBe('answer');
    if (event.type === 'answer') expect(event.payload.state).toBe('COMPLETED');
  });

  it('requires readiness checks to expose an explicit boolean', () => {
    expect(() => parseReadyResponse({ status: 'ready', checks: { qdrant: {} }, runtime: {} })).toThrow();
  });

  it('accepts the live readiness shape without treating check objects as booleans', () => {
    const parsed = parseReadyResponse({
      status: 'not_ready',
      checks: { qdrant: { ready: false, reason: 'offline' } },
      runtime: { process_instance_id: null, process_started_at: null, voice_requests_started: 0, rag_deadline_ms: 200, rag_fallback_at_ms: 170 },
    });
    expect(parsed.checks.qdrant.ready).toBe(false);
  });

  it('accepts corpus verification without inventing a corpus qualifying field', () => {
    const group = { status: 'not_measured', qualifying: false };
    const parsed = parseEvidenceSummary({
      schema_version: '2.0.0', generated_at: '2026-08-15T00:00:00Z',
      retrieval: { ...group, sample_count: 0 },
      corpus: { status: 'qualifying', verified: true },
      chunk_representations: [], dataset_audit: group, corpus_scaling: group,
      guardrails: group, voice_latency: group,
      provenance: { manifest_verified: true, audit_trail_valid: true, limitations: [] },
    });
    expect(parsed.corpus.verified).toBe(true);
  });
});
