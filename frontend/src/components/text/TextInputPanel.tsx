import React, { useState } from 'react';
import { CircleNotch, Eraser, Globe, Info, PaperPlaneRight } from '@phosphor-icons/react';
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
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
        <span className="flex items-center gap-1 text-xs text-slate-400"><Info size={14} className="text-cyan-400" />POST /v1/query/text</span>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-xs font-semibold text-slate-300"><Globe size={14} className="text-cyan-400" />Language hint</span>
          <div className="flex gap-1 rounded-lg border border-white/10 bg-white/5 p-1">
            {LANGUAGE_BUTTONS.map((language) => (
              <button key={language.id} type="button" disabled={disabled || isLoading} onClick={() => onLanguageChange(language.id)} className={`rounded-md px-2.5 py-1 text-xs disabled:opacity-50 ${selectedLanguage === language.id ? 'border border-cyan-400/30 bg-cyan-500/20 text-cyan-300' : 'text-slate-400 hover:text-white'}`}>{language.label}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="space-y-2">
        <label htmlFor="text-query-input" className="block text-xs font-bold text-slate-200">Ask a question grounded in the MSMARCO-XI corpus</label>
        <textarea id="text-query-input" rows={4} value={query} maxLength={MAX_CHARS} disabled={disabled || isLoading} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); submit(); } }} placeholder="Type a factual question in English, Hindi, or Hinglish..." className="min-h-[100px] w-full resize-y rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-400 disabled:opacity-60" />
        <div className="flex justify-between px-1 text-xs text-slate-400"><span>Ctrl+Enter to submit</span><span className="font-mono">{query.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}</span></div>
      </div>
      <div className="flex justify-end gap-3">
        <button type="button" onClick={() => setQuery('')} disabled={!query || isLoading} className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-semibold text-slate-300 disabled:opacity-40"><Eraser size={15} />Clear</button>
        <button type="button" onClick={submit} disabled={cannotSubmit} className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-6 py-2 text-xs font-bold text-white disabled:opacity-40">
          {isLoading ? <><CircleNotch size={15} className="animate-spin" />Querying...</> : <><PaperPlaneRight size={15} weight="bold" />Send question</>}
        </button>
      </div>
    </div>
  );
};
