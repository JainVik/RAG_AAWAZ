import React, { useMemo, useState } from 'react';
import {
  ArrowClockwise,
  ClockCounterClockwise,
  MagnifyingGlass,
  Sparkle,
  Trash,
} from '@phosphor-icons/react';
import type {
  VerifiedPrompt,
  VerifiedPromptCatalog,
  VerifiedPromptLanguage,
  VerifiedPromptLength,
  ServerLanguageCode,
} from '../../types/api';
import { getLanguageDisplayLabel } from '../../types/api';
import type { SessionQueryHistoryEntry } from '../../utils/sessionQueryHistory';
import { formatResponseLatency } from '../../utils/responseTiming';

export type QuestionLanguageFilter = 'all' | VerifiedPromptLanguage;
export type QuestionLengthFilter = 'all' | VerifiedPromptLength;
export type QuestionEnvironmentFilter = 'all' | 'clean' | 'noisy';

export interface QuestionFilters {
  search: string;
  language: QuestionLanguageFilter;
  length: QuestionLengthFilter;
  environment: QuestionEnvironmentFilter;
}

interface QuestionPaletteProps {
  catalog: VerifiedPromptCatalog | null;
  loading: boolean;
  error: string | null;
  recentQueries: SessionQueryHistoryEntry[];
  canSubmit: boolean;
  onAsk: (query: string, language: ServerLanguageCode) => void;
  onRetry: () => void;
  onClearRecent: () => void;
}

const LANGUAGE_LABELS: Record<VerifiedPromptLanguage, string> = {
  hi: 'Hindi',
  en: 'English',
  'hi-en': 'Hinglish',
};

const OUTCOME_LABELS: Record<SessionQueryHistoryEntry['outcome'], string> = {
  grounded: 'Grounded',
  abstained: 'No evidence',
  repeat: 'Repeat needed',
  blocked: 'Blocked',
  fallback: 'Fallback',
  unavailable: 'Unavailable',
  failed: 'Failed',
};

export function filterVerifiedPrompts(
  prompts: VerifiedPrompt[],
  filters: QuestionFilters,
): VerifiedPrompt[] {
  const search = filters.search.trim().toLocaleLowerCase();
  return prompts.filter((prompt) => {
    if (filters.language !== 'all' && prompt.language !== filters.language) return false;
    if (filters.length !== 'all' && prompt.length_class !== filters.length) return false;
    if (filters.environment !== 'all' && !prompt.condition.startsWith(filters.environment)) return false;
    if (!search) return true;
    return `${prompt.text} ${prompt.id}`.toLocaleLowerCase().includes(search);
  });
}

export const QuestionPalette: React.FC<QuestionPaletteProps> = ({
  catalog,
  loading,
  error,
  recentQueries,
  canSubmit,
  onAsk,
  onRetry,
  onClearRecent,
}) => {
  const [tab, setTab] = useState<'verified' | 'recent'>('verified');
  const [filters, setFilters] = useState<QuestionFilters>({
    search: '',
    language: 'all',
    length: 'all',
    environment: 'all',
  });
  const prompts = useMemo(
    () => filterVerifiedPrompts(catalog?.prompts ?? [], filters),
    [catalog, filters],
  );

  return (
    <div
      role="dialog"
      aria-label="Verified question gallery"
      className="refractive-glass-card refractive-glass-card-primary absolute bottom-full left-1/2 z-40 mb-3 flex max-h-[min(70dvh,38rem)] w-[min(94vw,46rem)] -translate-x-1/2 flex-col overflow-hidden shadow-2xl"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-white">
            <Sparkle size={15} className="text-blue-400" weight="fill" />
            Verified questions
          </div>
          <p className="mt-1 text-[10px] text-slate-400">
            Corpus-backed recording plan · not a measured voice result
          </p>
        </div>
        {catalog && (
          <span className="rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2.5 py-1 font-mono text-[10px] text-emerald-300">
            {catalog.live_text_validated_count}/{catalog.total} live-text validated
          </span>
        )}
      </div>

      <div className="flex gap-1 border-b border-white/10 px-3 pt-2" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'verified'}
          onClick={() => setTab('verified')}
          className={`rounded-t-lg px-3 py-2 text-xs font-semibold cursor-pointer transition-colors ${tab === 'verified' ? 'border-b-2 border-blue-400 text-blue-300' : 'text-slate-400 hover:text-white'}`}
        >
          Question gallery
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'recent'}
          onClick={() => setTab('recent')}
          className={`rounded-t-lg px-3 py-2 text-xs font-semibold cursor-pointer transition-colors ${tab === 'recent' ? 'border-b-2 border-blue-400 text-blue-300' : 'text-slate-400 hover:text-white'}`}
        >
          Recent this session ({recentQueries.length})
        </button>
      </div>

      {tab === 'verified' ? (
        <>
          <div className="space-y-2 border-b border-white/10 p-3">
            <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/20 px-3 py-2 focus-within:border-blue-400 focus-within:bg-black/30 backdrop-blur-sm transition-all">
              <MagnifyingGlass size={15} className="shrink-0 text-slate-400" />
              <span className="sr-only">Search verified questions</span>
              <input
                type="search"
                value={filters.search}
                onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
                placeholder="Search the 60 corpus-backed questions…"
                className="min-w-0 flex-1 bg-transparent text-xs text-white outline-none placeholder:text-slate-500"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <div className="flex rounded-lg border border-white/10 bg-black/20 p-0.5 backdrop-blur-sm">
                {(['all', 'hi', 'en', 'hi-en'] as const).map((language) => (
                  <button
                    key={language}
                    type="button"
                    onClick={() => setFilters((current) => ({ ...current, language }))}
                    className={`rounded-md px-2 py-1 text-[10px] font-semibold cursor-pointer transition-all ${filters.language === language ? 'bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white font-bold shadow-sm' : 'text-slate-400 hover:text-white'}`}
                  >
                    {language === 'all' ? 'All languages' : LANGUAGE_LABELS[language]}
                  </button>
                ))}
              </div>
              <select
                aria-label="Question length"
                value={filters.length}
                onChange={(event) => setFilters((current) => ({ ...current, length: event.target.value as QuestionLengthFilter }))}
                className="rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-[10px] text-slate-300 outline-none backdrop-blur-sm focus:border-blue-400"
              >
                <option value="all">Any length</option>
                <option value="short">Short</option>
                <option value="long">Long</option>
              </select>
              <select
                aria-label="Recording condition"
                value={filters.environment}
                onChange={(event) => setFilters((current) => ({ ...current, environment: event.target.value as QuestionEnvironmentFilter }))}
                className="rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-[10px] text-slate-300 outline-none backdrop-blur-sm focus:border-blue-400"
              >
                <option value="all">Clean or noisy</option>
                <option value="clean">Clean</option>
                <option value="noisy">Mild noise</option>
              </select>
            </div>
          </div>

          <div className="min-h-28 flex-1 overflow-y-auto p-3">
            {loading ? (
              <div className="flex h-28 items-center justify-center gap-2 text-xs text-slate-400">
                <ArrowClockwise size={16} className="animate-spin text-blue-400" />Loading verified questions…
              </div>
            ) : error ? (
              <div className="glass-inner-box flex h-32 flex-col items-center justify-center gap-3 px-4 text-center">
                <p className="text-xs text-slate-200">{error}</p>
                <button type="button" onClick={onRetry} className="glass-btn inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-200 cursor-pointer">
                  <ArrowClockwise size={14} />Retry
                </button>
              </div>
            ) : prompts.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {prompts.map((prompt) => (
                  <button
                    key={prompt.id}
                    type="button"
                    disabled={!canSubmit}
                    onClick={() => onAsk(prompt.text, prompt.language)}
                    className="group rounded-xl border border-white/10 bg-white/[0.04] p-3 text-left transition-all hover:border-blue-400/50 hover:bg-white/[0.08] hover:shadow-[0_4px_16px_rgba(37,99,235,0.15)] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                  >
                    <span className="flex items-center justify-between gap-2 font-mono text-[9px] uppercase tracking-wide">
                      <span className="text-blue-400 font-semibold">{LANGUAGE_LABELS[prompt.language]}</span>
                      <span className="text-slate-400">{prompt.condition.replace('-', ' · ')}</span>
                    </span>
                    <span className="mt-1.5 line-clamp-3 block text-xs leading-relaxed text-slate-200 group-hover:text-white transition-colors">
                      {prompt.text}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex h-28 items-center justify-center text-xs text-slate-500">No verified questions match these filters.</div>
            )}
          </div>
          {catalog && !loading && !error && (
            <div className="border-t border-white/10 px-4 py-2 text-[10px] text-slate-400">
              Showing {prompts.length} of {catalog.total} · Hindi {catalog.coverage.languages.hi} · English {catalog.coverage.languages.en} · Hinglish {catalog.coverage.languages['hi-en']}
            </div>
          )}
        </>
      ) : (
        <div className="min-h-48 flex-1 overflow-y-auto p-3">
          <div className="glass-inner-box mb-3 flex items-start justify-between gap-3 p-3">
            <div>
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-200">
                <ClockCounterClockwise size={14} className="text-blue-400" />Private session history
              </div>
              <p className="mt-1 text-[10px] leading-relaxed text-slate-400">Stored only in this browser tab. Text result metadata only; microphone audio is never stored here.</p>
            </div>
            <button
              type="button"
              disabled={!recentQueries.length}
              onClick={onClearRecent}
              className="glass-btn inline-flex shrink-0 items-center gap-1 px-2.5 py-1 text-[10px] text-slate-300 hover:text-white disabled:opacity-40 cursor-pointer"
            >
              <Trash size={12} />Clear
            </button>
          </div>
          {recentQueries.length ? (
            <div className="space-y-2">
              {recentQueries.map((entry) => (
                <button
                  key={entry.requestId}
                  type="button"
                  disabled={!canSubmit}
                  onClick={() => onAsk(entry.query, entry.language)}
                  className="w-full rounded-xl border border-white/10 bg-white/[0.04] p-3 text-left transition-all hover:border-blue-400/50 hover:bg-white/[0.08] hover:shadow-[0_4px_16px_rgba(37,99,235,0.15)] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                >
                  <span className="line-clamp-2 text-xs leading-relaxed text-slate-200">{entry.query}</span>
                  <span className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[9px] uppercase text-slate-400">
                    <span className="text-blue-400 font-semibold">{getLanguageDisplayLabel(entry.language)}</span>
                    <span>{OUTCOME_LABELS[entry.outcome]}</span>
                    <span>{entry.citationCount} citation{entry.citationCount === 1 ? '' : 's'}</span>
                    {entry.latencyMs !== null && <span>{formatResponseLatency(entry.latencyMs)}</span>}
                    <span className="ml-auto text-blue-300 font-medium">Ask again</span>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex h-28 flex-col items-center justify-center text-center">
              <ClockCounterClockwise size={22} className="mb-2 text-slate-500" />
              <p className="text-xs text-slate-300">No questions in this tab yet.</p>
              <p className="mt-1 text-[10px] text-slate-500">Completed voice and text queries will appear here.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
