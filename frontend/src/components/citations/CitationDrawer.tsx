import React, { useState } from 'react';
import {
  X,
  Quotes,
  Copy,
  Check,
  FileText,
  ShieldCheck,
  Hash,
  Sparkle,
  Code,
} from '@phosphor-icons/react';
import type { QueryResponse, Citation } from '../../types/api';

interface CitationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  result: QueryResponse | null;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({ isOpen, onClose, result }) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showRawDiagnostics, setShowRawDiagnostics] = useState<boolean>(false);

  if (!isOpen || !result) return null;

  const handleCopyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const citations: Citation[] = result.citations || [];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="citation-drawer-title"
      className="fixed inset-0 z-50 overflow-hidden"
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-6">
        <div className="w-screen max-w-lg bg-[#0e1424] border-l border-white/10 shadow-2xl flex flex-col justify-between text-white">
          {/* Header */}
          <div className="p-6 border-b border-white/10 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-cyan-400">
                <Quotes size={20} weight="fill" />
              </div>
              <div>
                <h2 id="citation-drawer-title" className="text-lg font-bold text-white tracking-tight">
                  Grounded Citations &amp; Evidence
                </h2>
                <p className="text-xs text-slate-400">
                  {citations.length} verified passage{citations.length !== 1 ? 's' : ''} from Goa Governance Index
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              <X size={20} />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="p-6 overflow-y-auto flex-1 space-y-6">
            {/* Grounding Verification Badge */}
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <ShieldCheck size={20} className="text-emerald-400" weight="fill" />
                <div>
                  <span className="text-xs font-bold text-emerald-300 block">
                    Grounded Extractive RAG Mode
                  </span>
                  <span className="text-[11px] text-emerald-400/80">
                    Extracted from Qdrant vector index with cosine similarity
                  </span>
                </div>
              </div>
              {result.agreement_score !== undefined && result.agreement_score !== null && (
                <span className="font-mono text-xs font-bold px-2 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  {(result.agreement_score * 100).toFixed(0)}% agreement
                </span>
              )}
            </div>

            {/* Citations List */}
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-400 uppercase tracking-wider">
                <span>Passage Excerpts</span>
                <span className="font-mono text-[10px] text-slate-500">Order by relevance</span>
              </div>

              {citations.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-400 border border-dashed border-white/10 rounded-xl">
                  No citations attached for this terminal state.
                </div>
              ) : (
                citations.map((c, idx) => (
                  <div
                    key={idx}
                    className="p-4 bg-white/5 hover:bg-white/[0.07] border border-white/10 rounded-xl space-y-3 transition-colors"
                  >
                    {/* Top Metadata row */}
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-1.5 font-mono text-cyan-400 text-[11px]">
                        <FileText size={14} />
                        <span className="truncate max-w-[200px]" title={c.document_id}>
                          {c.document_id}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-slate-300">
                        {c.strategy}
                      </span>
                    </div>

                    {/* Cited text */}
                    <p className="text-sm text-slate-200 leading-relaxed font-sans border-l-2 border-cyan-400/60 pl-3 py-0.5">
                      &ldquo;{c.cited_text}&rdquo;
                    </p>

                    {/* Coordinate Span & Scores */}
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-white/10 text-[11px] text-slate-400">
                      <div className="flex items-center gap-3 font-mono">
                        {c.char_start !== undefined && (
                          <span className="flex items-center gap-1">
                            <Hash size={12} />
                            <span>span: [{c.char_start}:{c.char_end}]</span>
                          </span>
                        )}
                        {c.dense_score !== undefined && c.dense_score !== null && (
                          <span className="flex items-center gap-1 text-cyan-300">
                            <Sparkle size={12} />
                            <span>dense: {c.dense_score.toFixed(3)}</span>
                          </span>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => handleCopyText(c.cited_text, `cite_${idx}`)}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-300 hover:text-white transition-colors cursor-pointer"
                      >
                        {copiedId === `cite_${idx}` ? (
                          <>
                            <Check size={13} className="text-emerald-400" />
                            <span>Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy size={13} />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Toggle Raw Sanitized JSON Diagnostics */}
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setShowRawDiagnostics(!showRawDiagnostics)}
                className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-cyan-400 transition-colors cursor-pointer"
              >
                <Code size={14} />
                <span>{showRawDiagnostics ? 'Hide Raw Diagnostics' : 'Show Sanitized JSON Diagnostics'}</span>
              </button>

              {showRawDiagnostics && (
                <pre className="mt-3 p-4 bg-black/50 border border-white/10 rounded-xl text-[11px] font-mono text-cyan-200 overflow-x-auto leading-relaxed max-h-60">
                  {JSON.stringify(
                    {
                      request_id: result.request_id,
                      state: result.state,
                      answer_mode: result.answer_mode,
                      language: result.language,
                      timings_ms: result.timings_ms,
                      guardrail: result.guardrail,
                      completed_at: result.completed_at,
                    },
                    null,
                    2
                  )}
                </pre>
              )}
            </div>
          </div>

          {/* Drawer Footer */}
          <div className="p-6 border-t border-white/10 bg-black/20 flex items-center justify-between text-xs text-slate-400">
            <span>Deterministic Grounded RAG</span>
            <button
              type="button"
              onClick={() => handleCopyText(JSON.stringify(result, null, 2), 'all_diag')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/15 text-white rounded-lg font-semibold transition-colors cursor-pointer"
            >
              {copiedId === 'all_diag' ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
              <span>Copy Response JSON</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
