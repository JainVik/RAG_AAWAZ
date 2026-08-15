import { describe, expect, it } from 'vitest';
import type { QueryResponse } from '../types/api';
import {
  prependSessionQuery,
  readSessionQueryHistory,
  SESSION_QUERY_HISTORY_KEY,
  toSessionQueryHistoryEntry,
  writeSessionQueryHistory,
} from './sessionQueryHistory';

function result(id: string, state: QueryResponse['state'] = 'COMPLETED'): QueryResponse {
  return {
    request_id: id,
    transcript: `Question ${id}`,
    language: 'hi-en',
    answer: state === 'COMPLETED' ? 'Answer' : null,
    answer_mode: state === 'COMPLETED' ? 'extractive' : 'abstention',
    citations: state === 'COMPLETED' ? [{
      canonical_doc_id: 'doc', parent_id: 'parent', chunk_id: 'chunk', strategy: 'atomic',
      text: 'Answer', span_start: 0, span_end: 6, span_coordinate_system: 'parent_text',
      source_text_sha256: 'a'.repeat(64), dense_score: 0.9, sparse_score: null,
    }] : [],
    guardrail: { decision: state === 'COMPLETED' ? 'ALLOW' : 'ABSTAIN', reason: null, evidence: {}, user_message: null },
    evidence_agreement: state === 'COMPLETED' ? 1 : null,
    state,
    timings_ms: { total_after_final_audio: 123.4 },
    completed_at: '2026-08-16T00:00:00Z',
  };
}

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

describe('session query history', () => {
  it('stores only the compact text outcome and backend latency', () => {
    expect(toSessionQueryHistoryEntry(result('one'))).toEqual({
      requestId: 'one', query: 'Question one', language: 'hi-en', outcome: 'grounded',
      citationCount: 1, latencyMs: 123.4, completedAt: '2026-08-16T00:00:00Z',
    });
  });

  it('deduplicates requests and keeps the ten newest entries', () => {
    let entries = Array.from({ length: 10 }, (_, index) => toSessionQueryHistoryEntry(result(String(index))));
    entries = prependSessionQuery(entries, toSessionQueryHistoryEntry(result('new')));
    expect(entries).toHaveLength(10);
    expect(entries[0].requestId).toBe('new');
    entries = prependSessionQuery(entries, toSessionQueryHistoryEntry(result('5')));
    expect(entries.filter((entry) => entry.requestId === '5')).toHaveLength(1);
    expect(entries[0].requestId).toBe('5');
  });

  it('round-trips valid entries while discarding corrupt browser data', () => {
    const storage = memoryStorage();
    const entries = [toSessionQueryHistoryEntry(result('one'))];
    writeSessionQueryHistory(entries, storage);
    expect(readSessionQueryHistory(storage)).toEqual(entries);
    storage.setItem(SESSION_QUERY_HISTORY_KEY, JSON.stringify([{ requestId: 'unsafe-shape' }]));
    expect(readSessionQueryHistory(storage)).toEqual([]);
  });
});
