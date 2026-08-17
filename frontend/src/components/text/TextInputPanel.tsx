import React, { useState } from 'react';
import { CircleNotch, Eraser, Globe, PaperPlaneRight } from '@phosphor-icons/react';
import type { LanguageHint } from '../../types/api';

interface TextInputPanelProps {
  isLoading: boolean;
  disabled?: boolean;
  selectedLanguage: LanguageHint;
  onLanguageChange: (language: LanguageHint) => void;
  onSubmit: (query: string) => void;
}

const MAX_CHARS = 4096;
const LANGUAGE_BUTTONS: { id: LanguageHint; label: string }[] = [
  { id: 'auto', label: 'Auto' },
  { id: 'hi', label: 'Hindi' },
  { id: 'hi-en', label: 'Hinglish' },
  { id: 'en', label: 'English' },
];

export const TextInputPanel: React.FC<TextInputPanelProps> = ({
  isLoading,
  disabled = false,
  selectedLanguage,
  onLanguageChange,
  onSubmit,
}) => {
  const [query, setQuery] = useState('');
  const cannotSubmit = disabled || isLoading || !query.trim();

  const submit = () => {
    if (!cannotSubmit) onSubmit(query.trim());
  };

  return (
    <div className="w-full space-y-6">
      <div className="flex flex-wrap items-center justify-end gap-4 border-b border-black/10 dark:border-white/10 pb-4">
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-xs font-semibold text-black dark:text-slate-300"><Globe size={14} className="text-blue-600 dark:text-blue-400" />Language hint</span>
          <div className="flex gap-1 rounded-lg border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-1 backdrop-blur-md">
            {LANGUAGE_BUTTONS.map((language) => (
              <button key={language.id} type="button" disabled={disabled || isLoading} onClick={() => onLanguageChange(language.id)} className={`rounded-md px-2.5 py-1 text-xs transition-all disabled:opacity-50 cursor-pointer ${selectedLanguage === language.id ? 'bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white font-bold shadow-[0_0_15px_rgba(37,99,235,0.4)]' : 'text-black hover:text-black dark:text-slate-400 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5'}`}>{language.label}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="space-y-2">
        <label htmlFor="text-query-input" className="block text-xs font-bold text-black dark:text-slate-200">Ask a question grounded in the MSMARCO-XI corpus</label>
        <textarea id="text-query-input" rows={4} value={query} maxLength={MAX_CHARS} disabled={disabled || isLoading} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); submit(); } }} placeholder="Type a factual question in English, Hindi, or Hinglish..." className="min-h-[110px] w-full resize-y rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.03] dark:bg-black/20 px-4 py-3 text-sm text-black dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-500 focus:border-blue-500 focus:bg-black/[0.06] dark:focus:bg-black/30 backdrop-blur-sm transition-all disabled:opacity-60" />
        <div className="flex justify-between px-1 text-xs text-black dark:text-slate-400"><span>Ctrl+Enter to submit</span><span className="font-mono font-semibold">{query.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}</span></div>
      </div>
      <div className="flex justify-end gap-3">
        <button type="button" onClick={() => setQuery('')} disabled={!query || isLoading} className="glass-btn inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-black dark:text-slate-300 disabled:opacity-40 cursor-pointer"><Eraser size={15} />Clear</button>
        <button type="button" onClick={submit} disabled={cannotSubmit} className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 px-6 py-2.5 text-xs font-bold text-white shadow-[0_0_20px_rgba(37,99,235,0.45)] hover:shadow-[0_0_25px_rgba(6,182,212,0.6)] cursor-pointer transform hover:scale-105 active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none">
          {isLoading ? <><CircleNotch size={15} className="animate-spin" />Querying...</> : <><PaperPlaneRight size={15} weight="bold" />Send question</>}
        </button>
      </div>
    </div>
  );
};
