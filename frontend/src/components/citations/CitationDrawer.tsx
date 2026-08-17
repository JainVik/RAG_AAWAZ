import React, { useEffect, useRef, useState } from 'react';
import { Check, Code, Copy, FileText, Hash, Quotes, ShieldCheck, X } from '@phosphor-icons/react';
import type { Citation } from '../../types/api';

interface CitationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  citations: Citation[];
  title: string;
  subtitle: string;
  badge: string;
  evidenceAgreement?: number | null;
  rawPayload: unknown;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({
  isOpen,
  onClose,
  citations,
  title,
  subtitle,
  badge,
  evidenceAgreement,
  rawPayload,
}) => {
  const [copied, setCopied] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;
  const copy = async (text: string, id: string) => { await navigator.clipboard.writeText(text); setCopied(id); window.setTimeout(() => setCopied(null), 1500); };

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="citation-title" className="fixed inset-0 z-50 overflow-hidden">
      <button type="button" aria-label="Close citations" onClick={onClose} className="fixed inset-0 bg-slate-900/20 dark:bg-black/30 backdrop-blur-[2px] cursor-pointer" />
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-6 pointer-events-none">
        <div className="refractive-glass-card refractive-glass-card-primary flex w-screen max-w-lg flex-col text-black dark:text-white shadow-2xl rounded-none rounded-l-2xl border-y-0 border-r-0 pointer-events-auto">
          <div className="flex items-center justify-between border-b border-black/10 dark:border-white/10 p-6">
            <div><h2 id="citation-title" className="flex items-center gap-2 text-lg font-bold"><Quotes className="text-blue-600 dark:text-blue-400" />{title}</h2><p className="text-xs text-black dark:text-slate-400">{subtitle}</p></div>
            <button
              ref={closeRef}
              type="button"
              aria-label="Close citation drawer"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onClose();
              }}
              className="relative z-20 rounded-lg p-1.5 text-slate-500 hover:text-black hover:bg-black/5 dark:text-slate-400 dark:hover:text-white dark:hover:bg-white/10 transition-colors cursor-pointer"
            >
              <X size={20} className="pointer-events-none" />
            </button>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto p-6">
            <div className="glass-inner-box flex items-center justify-between p-4 text-xs"><span className="flex items-center gap-2 font-bold text-blue-600 dark:text-blue-300"><ShieldCheck size={18} />{badge}</span>{evidenceAgreement !== null && evidenceAgreement !== undefined && <span className="font-mono text-black dark:text-slate-300">{(evidenceAgreement * 100).toFixed(0)}% branch agreement</span>}</div>
            {citations.map((citation) => (
              <article key={citation.chunk_id} className="space-y-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.03] dark:bg-white/[0.04] p-4 transition-all hover:border-blue-400/40 hover:bg-black/[0.06] dark:hover:bg-white/[0.07]">
                <div className="flex justify-between gap-2 text-[11px]"><span title={citation.canonical_doc_id} className="flex max-w-[250px] items-center gap-1 truncate font-mono text-blue-600 dark:text-blue-400"><FileText size={14} />{citation.canonical_doc_id}</span><span className="rounded-md border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/10 px-2 py-0.5 font-mono text-[10px] text-black dark:text-slate-300">{citation.strategy}</span></div>
                <p className="border-l-2 border-blue-500/60 dark:border-blue-400/60 pl-3 text-sm leading-relaxed text-black dark:text-slate-200">“{citation.text}”</p>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-black/10 dark:border-white/10 pt-2 text-[11px] text-black dark:text-slate-400">
                  <span className="flex items-center gap-1 font-mono"><Hash size={12} />{citation.span_coordinate_system} [{citation.span_start}:{citation.span_end}]</span>
                  <span className="font-mono">dense {citation.dense_score?.toFixed(3) ?? 'n/a'} · sparse {citation.sparse_score?.toFixed(3) ?? 'n/a'}</span>
                  <button type="button" onClick={() => void copy(citation.text, citation.chunk_id)} className="flex items-center gap-1 text-black hover:text-black dark:text-slate-300 dark:hover:text-white transition-colors cursor-pointer font-medium">{copied === citation.chunk_id ? <Check className="text-emerald-500" /> : <Copy />}Copy</button>
                </div>
              </article>
            ))}
            {!citations.length && <p className="glass-inner-box p-6 text-center text-xs text-black dark:text-slate-400">This response has no citations.</p>}
            <button type="button" onClick={() => setShowRaw(!showRaw)} className="flex items-center gap-1.5 text-xs text-black hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 transition-colors cursor-pointer font-medium"><Code size={14} />{showRaw ? 'Hide' : 'Show'} response JSON</button>
            {showRaw && <pre className="max-h-64 overflow-auto rounded-xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-black/40 p-4 text-[11px] text-black dark:text-blue-200 backdrop-blur-sm">{JSON.stringify(rawPayload, null, 2)}</pre>}
          </div>
          <div className="flex justify-between border-t border-black/10 dark:border-white/10 p-6 text-xs text-black dark:text-slate-400"><span>Exact source coordinates retained</span><button type="button" onClick={() => void copy(JSON.stringify(rawPayload, null, 2), 'all')} className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 px-3.5 py-1.5 text-xs font-bold text-white shadow-[0_0_15px_rgba(37,99,235,0.4)] hover:shadow-[0_0_20px_rgba(6,182,212,0.6)] cursor-pointer transform hover:scale-105 active:scale-95 transition-all">{copied === 'all' ? <Check className="text-white" weight="bold" /> : <Copy />}Copy JSON</button></div>
        </div>
      </div>
    </div>
  );
};
