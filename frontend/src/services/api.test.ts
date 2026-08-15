import { afterEach, describe, expect, it, vi } from 'vitest';
import { getOperationalMetrics, getVerifiedPrompts, sendSynthesis } from './api';

const completedSynthesis = {
  request_id: 'request-1',
  provider: 'groq',
  model: 'openai/gpt-oss-20b',
  status: 'completed',
  answer: 'Goa became a state in 1987.',
  claims: [{ text: 'Goa became a state in 1987.', citation_indices: [0] }],
  citations: [{
    canonical_doc_id: 'doc-1',
    parent_id: 'parent-1',
    chunk_id: 'chunk-1',
    strategy: 'atomic',
    text: 'Goa became a state in 1987.',
    span_start: 0,
    span_end: 32,
    span_coordinate_system: 'parent_text',
    source_text_sha256: 'a'.repeat(64),
    dense_score: 0.9,
    sparse_score: 0.7,
  }],
  guardrail: { decision: 'ALLOW', reason: null, evidence: {}, user_message: null },
  retryable: false,
  timings_ms: { groq_synthesis: 300, total_synthesis: 320 },
  completed_at: '2026-08-16T00:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('sendSynthesis', () => {
  it('posts the request-bound one-use offer and parses the grounded response', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify(completedSynthesis),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    ));
    vi.stubGlobal('fetch', fetchMock);
    const token = 'a'.repeat(43);

    const result = await sendSynthesis({ request_id: 'request-1', token });

    expect(result.status).toBe('completed');
    expect(result.answer).toBe('Goa became a state in 1987.');
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/query/synthesis');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ request_id: 'request-1', token });
  });
});

describe('getOperationalMetrics', () => {
  it('loads validated process-local metrics from the operations endpoint', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        requests_total: 3,
        latency_sample_count: 3,
        latency_ms: { p50: 80, p70: 90, p95: 100, p100: 110 },
        timings_ms: {},
        groq_synthesis: { latency_sample_count: 0 },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getOperationalMetrics();

    expect(result.latency_ms?.p50).toBe(80);
    expect(fetchMock).toHaveBeenCalledWith('/api/metrics', {
      headers: { Accept: 'application/json' },
    });
  });
});

describe('getVerifiedPrompts', () => {
  it('loads and validates the corpus-backed recording plan', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        schema_version: '1.0.0', catalog_id: 'msmarco-xi-human-voice-v1', status: 'recording_plan',
        total: 1, live_text_validated_count: 1,
        coverage: {
          languages: { hi: 0, en: 1, 'hi-en': 0 },
          conditions: { 'clean-short': 1, 'clean-long': 0, 'noisy-short': 0, 'noisy-long': 0 },
          lengths: { short: 1, long: 0 }, source_types: { human: 1 },
        },
        prompts: [{
          id: 'en-1', text: 'What is gold hardness?', language: 'en',
          condition: 'clean-short', length_class: 'short', source_query_id: 'q1',
        }],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getVerifiedPrompts();

    expect(result.prompts[0].language).toBe('en');
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/prompts/verified', {
      headers: { Accept: 'application/json' },
    });
  });
});
