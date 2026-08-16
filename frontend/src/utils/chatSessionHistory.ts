import type { QueryResponse, ServerLanguageCode, SynthesisResponse } from '../types/api';

export const CHAT_SESSION_STORAGE_KEY = 'vani-rag.chat-session.v1';
export const CHAT_TURNS_LIMIT = 20;

export interface ChatTurn {
  id: string;
  query: string;
  language: ServerLanguageCode;
  timestamp: string;
  source: 'voice' | 'text' | 'sample';
  result: QueryResponse;
  synthesisResult?: SynthesisResponse | null;
  synthesisLoading?: boolean;
  synthesisError?: string | null;
}

export function loadChatSession(): ChatTurn[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.sessionStorage.getItem(CHAT_SESSION_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(-CHAT_TURNS_LIMIT);
  } catch {
    return [];
  }
}

export function saveChatSession(turns: ChatTurn[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(
      CHAT_SESSION_STORAGE_KEY,
      JSON.stringify(turns.slice(-CHAT_TURNS_LIMIT))
    );
  } catch {
    // Graceful fallback for storage quota or private browsing
  }
}

export function clearChatSession(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(CHAT_SESSION_STORAGE_KEY);
  } catch {
    // Ignore
  }
}
