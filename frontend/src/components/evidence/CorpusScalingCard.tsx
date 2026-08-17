import React from 'react';
import {
  TrendUp,
  ClockCountdown,
  Database,
  Hash,
  Info,
} from '@phosphor-icons/react';
import type { CorpusScalingInfo } from '../../types/api';

interface CorpusScalingCardProps {
  scaling: CorpusScalingInfo;
}

export const CorpusScalingCard: React.FC<CorpusScalingCardProps> = ({ scaling }) => {
  const count = (value: number | null) => value === null ? 'Not measured' : value.toLocaleString();
  return (
    <article className="refractive-glass-card p-6 transition-all hover:border-blue-500/30">
      <div className="space-y-6">
        {/* Header & Status */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-black/10 dark:border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-400/20 text-blue-600 dark:text-blue-400">
              <TrendUp size={22} weight="bold" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-black dark:text-white tracking-tight">
                  Corpus Scaling &amp; Capacity Evidence
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-black/5 dark:bg-slate-800 text-black dark:text-slate-300 border border-black/10 dark:border-white/10">
                  {scaling.scaling_comparison_status}
                </span>
              </div>
              <p className="text-xs text-black dark:text-slate-400 mt-0.5">
                Baseline: {scaling.baseline_document_count?.toLocaleString() ?? 'not measured'} documents · comparison: {scaling.scaling_comparison_status}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-400/20 text-blue-600 dark:text-blue-300 text-xs font-mono">
            <ClockCountdown size={14} />
            <span>State: {scaling.status.toUpperCase()}</span>
          </div>
        </div>

        {/* Baseline Specification */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-3.5 bg-black/[0.03] dark:bg-white/5 border border-black/10 dark:border-white/8 rounded-xl space-y-1">
            <span className="text-[10px] font-bold text-black dark:text-slate-400 uppercase tracking-wider block">
              Baseline Documents
            </span>
            <span className="text-black dark:text-white font-mono font-bold text-base block">
              {count(scaling.baseline_document_count)}
            </span>
            <span className="text-[10px] text-black dark:text-slate-400 block">Verified source files</span>
          </div>

          <div className="p-3.5 bg-black/[0.03] dark:bg-white/5 border border-black/10 dark:border-white/8 rounded-xl space-y-1">
            <span className="text-[10px] font-bold text-black dark:text-slate-400 uppercase tracking-wider block">
              Indexed Points / Chunks
            </span>
            <span className="text-blue-600 dark:text-blue-400 font-mono font-bold text-base block">
              {count(scaling.baseline_chunk_count)}
            </span>
            <span className="text-[10px] text-black dark:text-slate-400 block">Reported baseline point count</span>
          </div>

          <div className="p-3.5 bg-black/[0.03] dark:bg-white/5 border border-black/10 dark:border-white/8 rounded-xl space-y-1">
            <span className="text-[10px] font-bold text-black dark:text-slate-400 uppercase tracking-wider block">
              Scaling Comparison Workflow
            </span>
            <span className="text-black dark:text-slate-200 font-bold text-xs block mt-1">
              Backend CLI Tooling
            </span>
            <span className="text-[10px] text-black dark:text-slate-400 block">No fabricated 25k/50k data</span>
          </div>
        </div>

        {/* Informative notice regarding CLI workflow vs UI buttons */}
        <div className="p-4 rounded-xl bg-black/[0.03] dark:bg-white/5 border border-black/10 dark:border-white/10 space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-black dark:text-slate-200">
            <Info size={16} className="text-blue-600 dark:text-blue-400" />
            <span>Multi-Corpus Scaling Policy</span>
          </div>
          <p className="text-xs text-black dark:text-slate-400 leading-relaxed">
            {scaling.notes ?? 'No scaling comparison artifact is available.'}
          </p>
        </div>

        {/* SHA256 Verification Footer */}
        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-2 border-t border-black/10 dark:border-white/8">
          <div className="flex items-center gap-1.5 truncate mr-4">
            <Hash size={12} className="text-slate-400 shrink-0" />
            <span className="text-black dark:text-slate-400">SHA256:</span>
            <span className="truncate text-black dark:text-slate-300">{scaling.source_artifact_sha256}</span>
          </div>
          <span className="shrink-0 text-black dark:text-slate-400 flex items-center gap-1">
            <Database size={12} />
            <span>{scaling.status.replaceAll('_', ' ')}</span>
          </span>
        </div>
      </div>
    </article>
  );
};
