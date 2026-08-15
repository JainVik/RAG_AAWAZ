import React, { useEffect, useRef, useState } from 'react';
import { Check, Code, Copy, FileText, Hash, Quotes, ShieldCheck, X } from '@phosphor-icons/react';
import type { QueryResponse } from '../../types/api';

interface CitationDrawerProps { isOpen: boolean; onClose: () => void; result: QueryResponse | null; }

export const CitationDrawer: React.FC<CitationDrawerProps> = ({ isOpen, onClose, result }) => {
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

  if (!isOpen || !result) return null;
  const copy = async (text: string, id: string) => { await navigator.clipboard.writeText(text); setCopied(id); window.setTimeout(() => setCopied(null), 1500); };

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="citation-title" className="fixed inset-0 z-50 overflow-hidden">
      <button type="button" aria-label="Close citations" onClick={onClose} className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm" />
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-6">
        <div className="flex w-screen max-w-lg flex-col bg-[#0e1424] text-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/10 p-6">
            <div><h2 id="citation-title" className="flex items-center gap-2 text-lg font-bold"><Quotes className="text-cyan-400" />Grounded citations</h2><p className="text-xs text-slate-400">{result.citations.length} exact evidence span{result.citations.length === 1 ? '' : 's'} from MSMARCO-XI</p></div>
            <button ref={closeRef} type="button" aria-label="Close citation drawer" onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:text-white"><X size={20} /></button>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto p-6">
            <div className="flex items-center justify-between rounded-xl border border-cyan-500/20 bg-cyan-500/10 p-4 text-xs"><span className="flex items-center gap-2 font-bold text-cyan-300"><ShieldCheck size={18} />{result.answer_mode}</span>{result.evidence_agreement !== null && <span>{(result.evidence_agreement * 100).toFixed(0)}% branch agreement</span>}</div>
            {result.citations.map((citation) => (
              <article key={citation.chunk_id} className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-4">
                <div className="flex justify-between gap-2 text-[11px]"><span title={citation.canonical_doc_id} className="flex max-w-[250px] items-center gap-1 truncate font-mono text-cyan-400"><FileText size={14} />{citation.canonical_doc_id}</span><span className="rounded bg-white/10 px-2 py-0.5">{citation.strategy}</span></div>
                <p className="border-l-2 border-cyan-400/60 pl-3 text-sm leading-relaxed text-slate-200">“{citation.text}”</p>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-2 text-[11px] text-slate-400">
                  <span className="flex items-center gap-1 font-mono"><Hash size={12} />{citation.span_coordinate_system} [{citation.span_start}:{citation.span_end}]</span>
                  <span className="font-mono">dense {citation.dense_score?.toFixed(3) ?? 'n/a'} · sparse {citation.sparse_score?.toFixed(3) ?? 'n/a'}</span>
                  <button type="button" onClick={() => void copy(citation.text, citation.chunk_id)} className="flex items-center gap-1 text-slate-300 hover:text-white">{copied === citation.chunk_id ? <Check className="text-emerald-400" /> : <Copy />}Copy</button>
                </div>
              </article>
            ))}
            {!result.citations.length && <p className="rounded-xl border border-dashed border-white/10 p-6 text-center text-xs text-slate-400">This terminal response has no citations.</p>}
            <button type="button" onClick={() => setShowRaw(!showRaw)} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-cyan-400"><Code size={14} />{showRaw ? 'Hide' : 'Show'} response JSON</button>
            {showRaw && <pre className="max-h-64 overflow-auto rounded-xl border border-white/10 bg-black/50 p-4 text-[11px] text-cyan-200">{JSON.stringify(result, null, 2)}</pre>}
          </div>
          <div className="flex justify-between border-t border-white/10 p-6 text-xs text-slate-400"><span>Exact source coordinates retained</span><button type="button" onClick={() => void copy(JSON.stringify(result, null, 2), 'all')} className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-white">{copied === 'all' ? <Check className="text-emerald-400" /> : <Copy />}Copy JSON</button></div>
        </div>
      </div>
    </div>
  );
};
