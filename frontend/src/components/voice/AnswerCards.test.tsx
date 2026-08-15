import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { QueryResponse, SynthesisResponse } from '../../types/api';
import { AnswerCards, sanitizeQueryResponseForDisplay } from './AnswerCards';

const citation = {
  canonical_doc_id: 'doc-1',
  parent_id: 'parent-1',
  chunk_id: 'chunk-1',
  strategy: 'atomic',
  text: 'Influenza is a viral respiratory illness.',
  span_start: 0,
  span_end: 41,
  span_coordinate_system: 'parent_text' as const,
  source_text_sha256: 'a'.repeat(64),
  dense_score: 0.8,
  sparse_score: null,
};

const primary: QueryResponse = {
  request_id: 'request-1',
  transcript: 'What is influenza?',
  language: 'en',
  answer: 'Influenza is a viral respiratory illness.',
  answer_mode: 'extractive',
  citations: [citation],
  guardrail: { decision: 'ALLOW', reason: null, evidence: {}, user_message: null },
  evidence_agreement: 1,
  state: 'COMPLETED',
  timings_ms: {
    input_guarded: 0.1,
    retrieved: 40,
    evidence_selected: 2,
    answered: 0.4,
    verified: 0.2,
    total_after_final_audio: 120,
  },
  completed_at: '2026-08-15T00:00:00Z',
};

const synthesis: SynthesisResponse = {
  request_id: 'request-1',
  provider: 'groq',
  model: 'openai/gpt-oss-20b',
  status: 'completed',
  answer: 'Influenza affects the respiratory system.',
  claims: [{ text: 'Influenza affects the respiratory system.', citation_indices: [0] }],
  citations: [citation],
  guardrail: { decision: 'ALLOW', reason: null, evidence: {}, user_message: null },
  retryable: false,
  timings_ms: { total_synthesis: 420 },
  completed_at: '2026-08-15T00:00:01Z',
};

function render(
  result: QueryResponse,
  options: {
    loading?: boolean;
    synthesisResult?: SynthesisResponse | null;
    error?: string | null;
  } = {}
) {
  return renderToStaticMarkup(
    <AnswerCards
      result={result}
      synthesisLoading={options.loading ?? false}
      synthesisResult={options.synthesisResult ?? null}
      synthesisError={options.error ?? null}
      onDismiss={() => undefined}
    />
  );
}

describe('AnswerCards', () => {
  it('keeps a single evidence card when an answer exists and synthesis is not offered', () => {
    const markup = render(primary);
    expect(markup).toContain('Evidence answer');
    expect(markup).not.toContain('Groq grounded synthesis');
  });

  it('spotlights the five measured core stages without replacing full response timing', () => {
    const markup = render(primary);
    expect(markup).toContain('Fast grounded path');
    expect(markup).toContain('42.7 ms');
    expect(markup).toContain('Core RAG stage subtotal');
    expect(markup).toContain('Hybrid search');
    expect(markup).toContain('Grounding');
    expect(markup).toContain('Full request 120 ms');
    expect(markup).toContain('Full latency evidence');
  });

  it('summarizes the user-facing outcome without exposing the raw terminal enum', () => {
    const markup = render(primary);
    expect(markup).toContain('Query outcome summary');
    expect(markup).toContain('English');
    expect(markup).toContain('Grounded');
    expect(markup).toContain('1 citation');
    expect(markup).toContain('120 ms');
    expect(markup).not.toContain('&gt;COMPLETED&lt;');
  });

  it('shows an adjacent out-of-context Groq card when no verified answer is available', () => {
    const markup = render({
      ...primary,
      answer: null,
      answer_mode: 'abstention',
      citations: [],
      guardrail: {
        decision: 'ABSTAIN',
        reason: 'NO_RELEVANT_EVIDENCE',
        evidence: {},
        user_message: 'The corpus does not contain enough verified evidence.',
      },
      evidence_agreement: null,
      state: 'ABSTAINED',
    });

    expect(markup).toContain('Evidence answer');
    expect(markup).toContain('Groq grounded synthesis');
    expect(markup).toContain('Out of context');
    expect(markup).toContain(
      'Groq was not invoked because no verified corpus evidence was available.'
    );
    expect(markup).toContain('lg:grid-cols-2');
  });

  it.each([
    {
      name: 'unsafe',
      state: 'UNSAFE',
      decision: 'BLOCK',
      reason: 'UNSAFE_REQUEST',
      message: 'Groq was not invoked because the request was blocked by safety checks.',
    },
    {
      name: 'repeat',
      state: 'NEEDS_REPEAT',
      decision: 'NEEDS_REPEAT',
      reason: 'LOW_STT_CONFIDENCE',
      message:
        'Groq was not invoked because the question needs to be repeated before a verified evidence answer can be prepared.',
    },
    {
      name: 'dependency failure',
      state: 'DEPENDENCY_UNAVAILABLE',
      decision: 'ABSTAIN',
      reason: 'DEPENDENCY_UNAVAILABLE',
      message: 'Groq was not invoked because a required service was unavailable.',
    },
  ] as const)('uses an accurate not-generated state for a $name outcome', (outcome) => {
    const result: QueryResponse = {
      ...primary,
      answer: null,
      answer_mode: 'abstention',
      citations: [],
      guardrail: {
        decision: outcome.decision,
        reason: outcome.reason,
        evidence: {},
        user_message: null,
      },
      evidence_agreement: null,
      state: outcome.state,
    };
    const markup = render(result);

    expect(markup).toContain('Groq grounded synthesis');
    expect(markup).toContain('Not generated');
    expect(markup).toContain(outcome.message);
    expect(markup).not.toContain('Out of context');
  });

  it('shows the primary answer immediately while synthesis is loading', () => {
    const offered = {
      ...primary,
      synthesis: {
        token: 'a'.repeat(43),
        provider: 'groq' as const,
        model: 'openai/gpt-oss-20b' as const,
        expires_in_ms: 30_000,
      },
    };
    const markup = render(offered, { loading: true });
    expect(markup).toContain(primary.answer);
    expect(markup).toContain('Preparing the grounded synthesis');
    expect(markup).toContain('lg:grid-cols-2');
  });

  it('renders an independently timed, grounded synthesis card', () => {
    const markup = render(
      { ...primary, synthesis: { token: 'a'.repeat(43), provider: 'groq', model: synthesis.model, expires_in_ms: 30_000 } },
      { synthesisResult: synthesis }
    );
    expect(markup).toContain(synthesis.answer);
    expect(markup).toContain('Generated in 420 ms');
    expect(markup).toContain('GPT OSS 20B');
    expect(markup).toContain('1 citation');
  });

  it('keeps the evidence answer visible when synthesis fails', () => {
    const unavailable: SynthesisResponse = {
      ...synthesis,
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
    const markup = render(primary, { synthesisResult: unavailable });
    expect(markup).toContain(primary.answer);
    expect(markup).toContain('Synthesis is temporarily unavailable.');
  });

  it('removes opaque synthesis tokens from drawer JSON payloads', () => {
    const token = 'private_token_'.padEnd(43, 'x');
    const sanitized = sanitizeQueryResponseForDisplay({
      ...primary,
      synthesis: {
        token,
        provider: 'groq',
        model: 'openai/gpt-oss-20b',
        expires_in_ms: 30_000,
      },
    });
    const serialized = JSON.stringify(sanitized);
    expect(serialized).not.toContain(token);
    expect(serialized).not.toContain('"token"');
    expect(serialized).toContain('"available":true');
  });
});
