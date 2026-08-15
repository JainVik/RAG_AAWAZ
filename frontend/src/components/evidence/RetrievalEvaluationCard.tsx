import React, { useState } from 'react';
import { ChartLineUp, ShieldCheck, CheckCircle, Info, Hash, Clock } from '@phosphor-icons/react';
import type { RetrievalMetrics } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface RetrievalEvaluationCardProps {
  metrics: RetrievalMetrics;
}

export const RetrievalEvaluationCard: React.FC<RetrievalEvaluationCardProps> = ({ metrics }) => {
  const [openMetricHelp, setOpenMetricHelp] = useState<string | null>(null);
  const percent = (value: number | null) => value === null ? 'Not measured' : `${(value * 100).toFixed(2)}%`;
  const latency = (value: number | null) => value === null ? 'Not measured' : `${value.toFixed(1)} ms`;
  const metricItems = [
    {
      label: 'Recall@1',
      value: percent(metrics.recall_at_1),
      desc: 'Relevant passage appears at rank 1',
    },
    {
      label: 'Recall@5',
      value: percent(metrics.recall_at_5),
      desc: 'Relevant passage appears in top 5',
    },
    {
      label: 'Recall@10',
      value: percent(metrics.recall_at_10),
      desc: 'Relevant passage appears in top 10',
    },
    {
      label: 'MRR@10',
      value: percent(metrics.mrr_at_10),
      desc: 'Mean reciprocal rank across retained test queries',
    },
    {
      label: 'nDCG@10',
      value: percent(metrics.ndcg_at_10),
      desc: 'Normalized discounted cumulative gain in top 10',
    },
  ];

  return (
    <GlassSurface
      borderRadius={20}
      brightness={35}
      opacity={0.85}
      className="p-6 sm:p-8 space-y-6 transition-all hover:border-cyan-500/30"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-400/20 text-cyan-400">
            <ChartLineUp size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
              <span>Final Held-Out Retrieval Evaluation</span>
              <span className="text-xs font-normal text-slate-400 font-mono">
                ({metrics.sample_count} queries)
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Artifact status: {metrics.status.replaceAll('_', ' ')} · {metrics.failure_count} execution failures
            </p>
          </div>
        </div>

        {/* Qualification Badge */}
        <div className="flex items-center gap-2">
          {metrics.qualifying ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 rounded-full text-xs font-semibold">
              <ShieldCheck size={14} weight="fill" className="text-emerald-400" />
              <span>Qualifying Held-Out Report</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-500/10 text-amber-300 border border-amber-500/30 rounded-full text-xs font-semibold">
              <Info size={14} />
              <span>Non-Qualifying</span>
            </span>
          )}
        </div>
      </div>

      {/* Primary Quality Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {metricItems.map((m, idx) => (
          <div
            key={idx}
            className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-1 hover:border-cyan-400/30 transition-colors"
          >
            <div className="flex items-center justify-between text-xs font-semibold text-slate-400">
              <span>{m.label}</span>
              <button
                type="button"
                aria-label={`Explain ${m.label}`}
                aria-expanded={openMetricHelp === m.label}
                onClick={() => setOpenMetricHelp((current) => current === m.label ? null : m.label)}
                onBlur={() => setOpenMetricHelp(null)}
                className="group relative cursor-help rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
              >
                <Info size={13} className="text-slate-500 group-hover:text-slate-300" />
                <span className={`${openMetricHelp === m.label ? 'block' : 'hidden group-hover:block'} absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-[#141d33] border border-white/15 rounded-lg text-[10px] text-slate-200 shadow-xl z-20 pointer-events-none`}>
                  {m.desc}
                </span>
              </button>
            </div>
            <div className="font-mono text-xl sm:text-2xl font-bold text-cyan-300 font-mono-tabular">
              {m.value}
            </div>
            <p className="text-[10px] text-slate-400 truncate" title={m.desc}>
              {m.desc}
            </p>
          </div>
        ))}
      </div>

      {/* Direct Retrieval Evaluation Latency Section */}
      <div className="p-4 rounded-xl bg-white/5 border border-white/8 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
            <Clock size={16} className="text-cyan-400" />
            <span>Direct Retrieval Evaluation Latency ({metrics.direct_latency_sample_count ?? 0} rows)</span>
          </div>
          <span className="text-[10px] font-mono text-slate-400">
            Direct index evaluation • Distinct from end-to-end voice latency
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center">
          <div className="p-2.5 bg-white/5 rounded-lg border border-white/5">
            <span className="text-[10px] text-slate-400 uppercase font-bold block">P50 Latency</span>
            <span className="text-sm font-mono font-bold text-white">{latency(metrics.direct_p50_ms)}</span>
          </div>
          <div className="p-2.5 bg-white/5 rounded-lg border border-white/5">
            <span className="text-[10px] text-slate-400 uppercase font-bold block">P70 Latency</span>
            <span className="text-sm font-mono font-bold text-white">{latency(metrics.direct_p70_ms)}</span>
          </div>
          <div className="p-2.5 bg-white/5 rounded-lg border border-white/5">
            <span className="text-[10px] text-slate-400 uppercase font-bold block">P95 Latency</span>
            <span className="text-sm font-mono font-bold text-white">{latency(metrics.direct_p95_ms)}</span>
          </div>
          <div className="p-2.5 bg-white/5 rounded-lg border border-white/5">
            <span className="text-[10px] text-slate-400 uppercase font-bold block">Max Latency</span>
            <span className="text-sm font-mono font-bold text-cyan-300">{latency(metrics.direct_max_ms)}</span>
          </div>
        </div>
      </div>

      {/* Detailed Report Attributes */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        <div className="p-3 bg-white/5 border border-white/8 rounded-xl flex items-center justify-between">
          <span className="text-slate-400">Hit Coverage:</span>
          <span className="font-mono font-bold text-white">
            {percent(metrics.retrieval_hit_coverage)}
          </span>
        </div>
        <div className="p-3 bg-white/5 border border-white/8 rounded-xl flex items-center justify-between">
          <span className="text-slate-400">Execution Failures:</span>
          <span className="font-mono font-bold text-emerald-400 flex items-center gap-1">
            <CheckCircle size={14} weight="fill" />
            <span>{metrics.failure_count}</span>
          </span>
        </div>
        <div className="p-3 bg-white/5 border border-white/8 rounded-xl flex items-center justify-between">
          <span className="text-slate-400">Split Provenance:</span>
          <span className="font-mono font-bold text-cyan-300">
            {metrics.split_verified ? 'Verified Frozen Split' : 'Unverified'}
          </span>
        </div>
      </div>

      {/* Artifact SHA256 */}
      <div className="flex items-center gap-2 text-[10px] text-slate-400 pt-2 border-t border-white/8 font-mono">
        <Hash size={13} className="text-cyan-400 shrink-0" />
        <span className="text-slate-500">Source Report SHA256:</span>
        <span className="truncate text-slate-300" title={metrics.source_artifact_sha256 ?? undefined}>
          {metrics.source_artifact_sha256 ?? 'Not available'}
        </span>
      </div>
    </GlassSurface>
  );
};
