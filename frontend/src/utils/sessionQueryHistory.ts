import type { QueryResponse, ServerLanguageCode } from '../types/api';
import { getResponseLatencyMs } from './responseTiming';

export const SESSION_QUERY_HISTORY_KEY = 'vani-rag.session-query-history.v1';
export const SESSION_QUERY_HISTORY_LIMIT = 10;

export type SessionQueryOutcome =
  | 'grounded'
  | 'abstained'
  | 'repeat'
  | 'blocked'
  | 'fallback'
  | 'unavailable'
  | 'failed';

export interface SessionQueryHistoryEntry {
  requestId: string;
  query: string;
  language: ServerLanguageCode;
  outcome: SessionQueryOutcome;
  citationCount: number;
  latencyMs: number | null;
  completedAt: string;
}

interface SessionStorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
}

const LANGUAGE_CODES = new Set<ServerLanguageCode>([
  'unknown', 'as', 'bn', 'gu', 'hi', 'en', 'kn', 'ml', 'mr', 'ne', 'or', 'pa', 'sa', 'ta',
  'te', 'ur', 'hi-en',
]);
const OUTCOMES = new Set<SessionQueryOutcome>([
  'grounded', 'abstained', 'repeat', 'blocked', 'fallback', 'unavailable', 'failed',
]);

function isStoredEntry(value: unknown): value is SessionQueryHistoryEntry {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.requestId === 'string' && entry.requestId.length > 0 &&
    typeof entry.query === 'string' && entry.query.trim().length > 0 &&
    typeof entry.language === 'string' && LANGUAGE_CODES.has(entry.language as ServerLanguageCode) &&
    typeof entry.outcome === 'string' && OUTCOMES.has(entry.outcome as SessionQueryOutcome) &&
    typeof entry.citationCount === 'number' && Number.isInteger(entry.citationCount) && entry.citationCount >= 0 &&
    (entry.latencyMs === null ||
      (typeof entry.latencyMs === 'number' && Number.isFinite(entry.latencyMs) && entry.latencyMs >= 0)) &&
    typeof entry.completedAt === 'string' && entry.completedAt.length > 0
  );
}

export function getSessionQueryOutcome(result: QueryResponse): SessionQueryOutcome {
  if (result.state === 'COMPLETED' && result.answer && result.citations.length > 0) return 'grounded';
  if (result.state === 'ABSTAINED') return 'abstained';
  if (result.state === 'NEEDS_REPEAT') return 'repeat';
  if (result.state === 'UNSAFE') return 'blocked';
  if (result.state === 'DEADLINE_FALLBACK') return 'fallback';
  if (result.state === 'DEPENDENCY_UNAVAILABLE') return 'unavailable';
  return 'failed';
}

export function toSessionQueryHistoryEntry(result: QueryResponse): SessionQueryHistoryEntry {
  return {
    requestId: result.request_id,
    query: result.transcript.trim(),
    language: result.language,
    outcome: getSessionQueryOutcome(result),
    citationCount: result.citations.length,
    latencyMs: getResponseLatencyMs(result.timings_ms),
    completedAt: result.completed_at,
  };
}

export function prependSessionQuery(
  entries: SessionQueryHistoryEntry[],
  entry: SessionQueryHistoryEntry,
): SessionQueryHistoryEntry[] {
  return [entry, ...entries.filter((item) => item.requestId !== entry.requestId)]
    .slice(0, SESSION_QUERY_HISTORY_LIMIT);
}

export function readSessionQueryHistory(
  storage?: SessionStorageLike | null,
): SessionQueryHistoryEntry[] {
  try {
    const target = storage === undefined
      ? (typeof window === 'undefined' ? null : window.sessionStorage)
      : storage;
    if (!target) return [];
    const raw = target.getItem(SESSION_QUERY_HISTORY_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isStoredEntry).slice(0, SESSION_QUERY_HISTORY_LIMIT);
  } catch {
    return [];
  }
}

export function writeSessionQueryHistory(
  entries: SessionQueryHistoryEntry[],
  storage?: SessionStorageLike | null,
): void {
  try {
    const target = storage === undefined
      ? (typeof window === 'undefined' ? null : window.sessionStorage)
      : storage;
    if (!target) return;
    target.setItem(SESSION_QUERY_HISTORY_KEY, JSON.stringify(entries.slice(0, SESSION_QUERY_HISTORY_LIMIT)));
  } catch {
    // Session history is a progressive enhancement and must never block querying.
  }
}

export function removeSessionQueryHistory(
  storage?: SessionStorageLike | null,
): void {
  try {
    const target = storage === undefined
      ? (typeof window === 'undefined' ? null : window.sessionStorage)
      : storage;
    if (!target) return;
    target.removeItem(SESSION_QUERY_HISTORY_KEY);
  } catch {
    // Browsers may deny storage in hardened privacy modes.
  }
}
