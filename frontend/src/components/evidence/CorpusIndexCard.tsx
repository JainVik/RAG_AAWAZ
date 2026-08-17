import React from 'react';
import { CaretDown, Database, Cpu, HardDrives, ShieldCheck } from '@phosphor-icons/react';
import type { CorpusIndexInfo } from '../../types/api';

interface CorpusIndexCardProps {
  corpus: CorpusIndexInfo;
}

export const CorpusIndexCard: React.FC<CorpusIndexCardProps> = ({ corpus }) => {
  const count = (value: number | null) => value === null ? 'Not available' : value.toLocaleString();
  return (
    <article className="refractive-glass-card refractive-glass-card-primary p-6 sm:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-black/10 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-blue-500/10 dark:bg-blue-500/15 border border-blue-400/30 text-blue-600 dark:text-blue-300">
            <Database size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-bold text-black dark:text-white tracking-tight flex items-center gap-2">
              <span>Corpus → vector index</span>
            </h2>
            <p className="text-xs text-black dark:text-slate-400">
              Verified source passages expanded into retrieval-ready representations
            </p>
          </div>
        </div>

        <span className={`inline-flex items-center gap-1.5 px-3 py-1 border rounded-full text-xs font-semibold ${corpus.verified ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30' : 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30'}`}>
          <ShieldCheck size={14} weight="fill" className="text-emerald-600 dark:text-emerald-400" />
          <span>{corpus.verified ? 'Manifest verified' : corpus.status.replaceAll('_', ' ')}</span>
        </span>
      </div>

      {/* Corpus Facts Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-4 bg-black/[0.03] dark:bg-white/[0.04] border border-black/10 dark:border-white/10 rounded-xl space-y-1 transition-all hover:bg-black/[0.06] dark:hover:bg-white/[0.07]">
          <div className="flex items-center gap-1.5 text-xs text-black dark:text-slate-400 font-semibold">
            <HardDrives size={15} className="text-blue-600 dark:text-blue-400" />
            <span>Corpus Documents</span>
          </div>
          <div className="font-mono text-2xl font-bold text-black dark:text-white font-mono-tabular">
            {count(corpus.document_count)}
          </div>
          <p className="text-[11px] text-black dark:text-slate-400">
            Unique corpus passages
          </p>
        </div>

        <div className="p-4 bg-black/[0.03] dark:bg-white/[0.04] border border-black/10 dark:border-white/10 rounded-xl space-y-1 transition-all hover:bg-black/[0.06] dark:hover:bg-white/[0.07]">
          <div className="flex items-center gap-1.5 text-xs text-black dark:text-slate-400 font-semibold">
            <Database size={15} className="text-blue-600 dark:text-blue-400" />
            <span>Indexed Chunks</span>
          </div>
          <div className="font-mono text-2xl font-bold text-blue-600 dark:text-blue-300 font-mono-tabular">
            {count(corpus.indexed_chunks_count)}
          </div>
          <p className="text-[11px] text-black dark:text-slate-400">
            Vector points across enabled representations
          </p>
        </div>

        <div className="p-4 bg-black/[0.03] dark:bg-white/[0.04] border border-black/10 dark:border-white/10 rounded-xl space-y-1 transition-all hover:bg-black/[0.06] dark:hover:bg-white/[0.07]">
          <div className="flex items-center gap-1.5 text-xs text-black dark:text-slate-400 font-semibold">
            <ShieldCheck size={15} className="text-emerald-600 dark:text-emerald-400" />
            <span>Evaluation Fixtures</span>
          </div>
          <div className="font-mono text-2xl font-bold text-black dark:text-white font-mono-tabular">
            {count(corpus.evaluation_fixture_count)}
          </div>
          <p className="text-[11px] text-black dark:text-slate-400">
            Annotated test pairs with ground truth passage IDs
          </p>
        </div>
      </div>

      <details className="glass-inner-box overflow-hidden">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-bold text-black dark:text-slate-200">
          <span>Evaluator details · embedding and index bindings</span>
          <CaretDown size={15} className="text-slate-400" />
        </summary>
        <div className="mt-3 grid grid-cols-1 gap-4 border-t border-black/10 dark:border-white/10 pt-3 sm:grid-cols-2">
          <div className="space-y-2.5 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.03] dark:bg-white/[0.04] p-4">
            <div className="flex items-center gap-2 text-xs font-bold text-blue-600 dark:text-blue-300">
              <Cpu size={16} />
              <span>Dense embedding</span>
            </div>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between gap-3"><span className="text-black dark:text-slate-400">Model</span><span className="text-right font-mono font-semibold text-black dark:text-white">{corpus.dense_model}</span></div>
              <div className="flex justify-between gap-3"><span className="text-black dark:text-slate-400">Dimension / metric</span><span className="font-mono text-blue-600 dark:text-blue-300">{corpus.dense_dim}d / {corpus.dense_distance}</span></div>
              <div className="flex justify-between gap-3"><span className="text-black dark:text-slate-400">Corpus language</span><span className="font-mono text-black dark:text-white">{corpus.language}</span></div>
            </div>
          </div>
          <div className="space-y-2.5 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.03] dark:bg-white/[0.04] p-4">
            <div className="flex items-center gap-2 text-xs font-bold text-blue-600 dark:text-blue-300">
              <Database size={16} />
              <span>Vector and sparse index</span>
            </div>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between gap-3"><span className="text-black dark:text-slate-400">Collection</span><span className="text-right font-mono font-semibold text-black dark:text-white">{corpus.qdrant_collection}</span></div>
              <div className="flex justify-between gap-3"><span className="text-black dark:text-slate-400">Sparse model</span><span className="text-right font-mono text-black dark:text-white">{corpus.sparse_model}</span></div>
              <div className="flex justify-between gap-3"><span className="text-black dark:text-slate-400">Revision</span><span className="max-w-52 truncate font-mono text-blue-600 dark:text-blue-300" title={corpus.revision ?? undefined}>{corpus.revision ?? 'Not available'}</span></div>
              <div className="flex justify-between gap-3"><span className="text-black dark:text-slate-400">Build ID</span><span className="max-w-52 truncate font-mono text-black dark:text-slate-300" title={corpus.index_build_id ?? undefined}>{corpus.index_build_id ?? 'Not available'}</span></div>
            </div>
          </div>
        </div>
      </details>
    </article>
  );
};
