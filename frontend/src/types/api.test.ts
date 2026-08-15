import { describe, expect, it } from 'vitest';
import { getLanguageDisplayLabel, LANGUAGE_REGISTRY, parseEvidenceSummary, parseOperationalMetrics, parseQueryResponse, parseReadyResponse, parseSynthesisResponse, parseVoiceServerEvent, toBackendLanguage } from './api';

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

const synthesisResponse = {
  request_id: 'request-1',
  provider: 'groq',
  model: 'openai/gpt-oss-20b',
  status: 'completed',
  answer: 'Influenza is a respiratory illness.',
  claims: [{ text: 'Influenza is a respiratory illness.', citation_indices: [0] }],
  citations: queryResponse.citations,
  guardrail: { decision: 'ALLOW', reason: null, evidence: {}, user_message: null },
  retryable: false,
  timings_ms: { total_synthesis: 415.2, groq_synthesis: 390.1 },
  completed_at: '2026-08-15T00:00:01Z',
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

  it('accepts a progressive synthesis offer while preserving responses without one', () => {
    const token = 'a'.repeat(43);
    expect(parseQueryResponse(queryResponse).synthesis).toBeUndefined();
    expect(parseQueryResponse({
      ...queryResponse,
      synthesis: {
        token,
        provider: 'groq',
        model: 'openai/gpt-oss-20b',
        expires_in_ms: 30_000,
      },
    }).synthesis?.token).toBe(token);
    expect(() => parseQueryResponse({
      ...queryResponse,
      synthesis: {
        token: 'too-short',
        provider: 'groq',
        model: 'openai/gpt-oss-20b',
        expires_in_ms: 0,
      },
    })).toThrow();
    expect(() => parseQueryResponse({
      ...queryResponse,
      synthesis: {
        token,
        provider: 'groq',
        model: 'openai/gpt-oss-20b',
        expires_in_ms: 600_001,
      },
    })).toThrow();
  });

  it('parses a completed, citation-grounded Groq synthesis response', () => {
    const parsed = parseSynthesisResponse(synthesisResponse);
    expect(parsed.status).toBe('completed');
    expect(parsed.claims[0].citation_indices).toEqual([0]);
    expect(parsed.timings_ms.total_synthesis).toBe(415.2);
  });

  it('rejects synthesis responses that violate grounding invariants', () => {
    expect(() => parseSynthesisResponse({ ...synthesisResponse, answer: null })).toThrow();
    expect(() => parseSynthesisResponse({ ...synthesisResponse, claims: [] })).toThrow();
    expect(() => parseSynthesisResponse({
      ...synthesisResponse,
      claims: [{ text: 'Claim', citation_indices: [0, 0] }],
    })).toThrow();
    expect(() => parseSynthesisResponse({
      ...synthesisResponse,
      claims: [{ text: 'Claim', citation_indices: [1] }],
    })).toThrow();
    expect(() => parseSynthesisResponse({
      ...synthesisResponse,
      guardrail: { ...synthesisResponse.guardrail, decision: 'ABSTAIN' },
    })).toThrow();
    expect(() => parseSynthesisResponse({ ...synthesisResponse, retryable: true })).toThrow();
  });

  it('accepts empty terminal synthesis failures and rejects leaked drafts', () => {
    const unavailable = {
      ...synthesisResponse,
      status: 'unavailable',
      answer: null,
      claims: [],
      citations: [],
      guardrail: {
        decision: 'WARN',
        reason: 'DEPENDENCY_UNAVAILABLE',
        evidence: {},
        user_message: 'Synthesis is temporarily unavailable.',
      },
      retryable: false,
    };
    expect(parseSynthesisResponse(unavailable).status).toBe('unavailable');
    expect(() => parseSynthesisResponse({ ...unavailable, answer: 'unverified draft' })).toThrow();
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

  it('parses finite process-local latency percentiles and per-stage sample counts', () => {
    const parsed = parseOperationalMetrics({
      requests_total: 10,
      latency_sample_count: 9,
      latency_ms: { p50: 80, p70: 95, p95: 140, p100: 180 },
      timings_ms: {
        retrieved: { count: 9, p50: 40, p70: 55, p95: 90, p100: 120 },
      },
      groq_synthesis: {
        latency_sample_count: 2,
        latency_ms: { p50: 500, p70: 520, p95: 550, p100: 550 },
      },
    });
    expect(parsed.latency_ms?.p95).toBe(140);
    expect(parsed.timings_ms.retrieved.count).toBe(9);
    expect(parsed.groq_synthesis.latency_ms?.p50).toBe(500);
  });

  it('rejects malformed or negative operational latency evidence', () => {
    const base = {
      requests_total: 1,
      latency_sample_count: 1,
      latency_ms: { p50: 10, p70: 11, p95: 12, p100: 13 },
      timings_ms: {},
      groq_synthesis: { latency_sample_count: 0 },
    };
    expect(() => parseOperationalMetrics({ ...base, latency_sample_count: -1 })).toThrow();
    expect(() => parseOperationalMetrics({
      ...base,
      timings_ms: { retrieved: { count: 1, p50: 1, p70: 2, p95: Number.NaN, p100: 4 } },
    })).toThrow();
  });
});
