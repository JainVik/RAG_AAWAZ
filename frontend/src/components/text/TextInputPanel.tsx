import React, { useState } from 'react';
import { PaperPlaneRight, Eraser, Globe, Info, CircleNotch } from '@phosphor-icons/react';
import type { Language } from '../../types/api';

interface TextInputPanelProps {
  isLoading: boolean;
  selectedLanguage: Language;
  onLanguageChange: (lang: Language) => void;
  onSubmit: (query: string) => void;
}

const MAX_CHARS = 4096;

export const TextInputPanel: React.FC<TextInputPanelProps> = ({
  isLoading,
  selectedLanguage,
  onLanguageChange,
  onSubmit,
}) => {
  const [query, setQuery] = useState('');

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (query.trim() && !isLoading) {
        onSubmit(query.trim());
      }
    }
  };

  const handleClear = () => {
    setQuery('');
  };

  const charCount = query.length;
  const isNearLimit = charCount > MAX_CHARS * 0.9;
  const isOverLimit = charCount > MAX_CHARS;

  return (
    <div className="w-full space-y-6">
      {/* Header bar: Mode Notice & Language Hint */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div className="flex items-center gap-2">
          <div className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[11px] font-bold text-slate-300 tracking-wide uppercase font-mono">
            Deterministic Text Query
          </div>
          <span className="text-xs text-slate-400 flex items-center gap-1">
            <Info size={14} className="text-cyan-400" />
            <span>Sends real request to <code className="font-mono text-cyan-300">POST /v1/query/text</code></span>
          </span>
        </div>

        {/* Language hint */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
            <Globe size={14} className="text-cyan-400" />
            <span>Language:</span>
          </span>
          <div className="flex items-center gap-1 bg-white/5 p-1 rounded-lg border border-white/10">
            {(
              [
                { id: 'auto' as Language, label: 'Auto' },
                { id: 'hi' as Language, label: 'हिंदी' },
                { id: 'en' as Language, label: 'English' },
                { id: 'mr' as Language, label: 'मराठी' },
              ]
            ).map((lang) => (
              <button
                key={lang.id}
                type="button"
                onClick={() => onLanguageChange(lang.id)}
                disabled={isLoading}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all cursor-pointer disabled:opacity-50 ${
                  selectedLanguage === lang.id
                    ? 'bg-cyan-500/20 text-cyan-300 shadow-xs font-semibold border border-cyan-400/30'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Multiline Question Input */}
      <div className="space-y-2">
        <label htmlFor="text-query-input" className="block text-xs font-bold text-slate-200">
          Ask your question about Goa governance:
        </label>
        <div className="relative">
          <textarea
            id="text-query-input"
            rows={4}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder="Type your question about Goa administrative rules, water policies, certificates..."
            maxLength={MAX_CHARS}
            className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder:text-slate-500 focus:bg-white/10 focus:border-cyan-400 transition-all resize-y min-h-[100px] leading-relaxed font-sans"
          />
        </div>

        {/* Character count indicator */}
        <div className="flex items-center justify-between text-xs px-1">
          <span className="text-slate-400">
            Press <kbd className="font-mono bg-white/5 border border-white/10 px-1.5 py-0.5 rounded text-[10px] font-semibold text-slate-300">Ctrl+Enter</kbd> to submit
          </span>
          <span
            className={`font-mono font-medium ${
              isOverLimit
                ? 'text-rose-400 font-bold'
                : isNearLimit
                ? 'text-amber-400 font-semibold'
                : 'text-slate-400'
            }`}
          >
            {charCount.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={handleClear}
          disabled={!query || isLoading}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-white/5 border border-white/10 text-slate-300 hover:text-white hover:bg-white/10 rounded-xl text-xs font-semibold transition-all disabled:opacity-40 cursor-pointer"
        >
          <Eraser size={15} />
          <span>Clear</span>
        </button>

        <button
          type="button"
          onClick={() => query.trim() && onSubmit(query.trim())}
          disabled={!query.trim() || isLoading}
          className="inline-flex items-center gap-2 px-6 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl text-xs font-bold shadow-sm transition-all disabled:opacity-40 cursor-pointer"
        >
          {isLoading ? (
            <>
              <CircleNotch size={15} className="animate-spin" />
              <span>Querying backend...</span>
            </>
          ) : (
            <>
              <PaperPlaneRight size={15} weight="bold" />
              <span>Send question</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
