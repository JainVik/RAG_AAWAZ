import React from 'react';
import { ArrowSquareOut, Gauge, Lightning } from '@phosphor-icons/react';
import { formatStageLatency, getCoreLatencySummary } from '../../utils/pipelineLatency';
import { formatResponseLatency } from '../../utils/responseTiming';

interface QueryLatencySummaryProps {
  timingsMs: Record<string, number>;
}

export const QueryLatencySummary: React.FC<QueryLatencySummaryProps> = ({ timingsMs }) => {
  const summary = getCoreLatencySummary(timingsMs);
  const measuredStages = summary?.stages.filter((stage) => stage.durationMs !== null) ?? [];
  if (!summary || measuredStages.length === 0) return null;

  return (
    <aside
      aria-label="Per-query core RAG latency"
      className="mt-4 overflow-hidden rounded-2xl border border-cyan-400/20 bg-[#091322]/90 shadow-xl"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/8 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2">
          <span className="rounded-lg border border-cyan-400/20 bg-cyan-500/10 p-1.5 text-cyan-300">
            <Lightning size={16} weight="fill" />
          </span>
          <div>
            <p className="text-xs font-bold text-white">Fast grounded path</p>
            <p className="text-[10px] text-slate-500">Measured backend stages for this query</p>
          </div>
        </div>
        {summary.subtotalMs !== null ? (
          <div className="text-right">
            <p className="font-mono text-lg font-bold text-cyan-300">
              {formatStageLatency(summary.subtotalMs)}
            </p>
            <p className="text-[9px] uppercase tracking-wider text-slate-500">
              Core RAG stage subtotal
            </p>
          </div>
        ) : (
          <span className="rounded-full border border-amber-400/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold text-amber-200">
            Partial path · {measuredStages.length}/5 stages
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-px bg-white/5 sm:grid-cols-5">
        {measuredStages.map((stage) => (
          <div key={stage.key} className="min-w-0 bg-[#0c1627] px-3 py-3 text-left">
            <p className="truncate text-[9px] font-semibold uppercase tracking-wider text-slate-500" title={stage.label}>
              {stage.shortLabel}
            </p>
            <p className="mt-1 font-mono text-sm font-bold text-white">
              {formatStageLatency(stage.durationMs ?? 0)}
            </p>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2 px-4 py-2.5 text-[9px] leading-relaxed text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <span className="inline-flex items-start gap-1.5">
          <Gauge size={12} className="mt-0.5 shrink-0 text-cyan-400" />
          Core subtotal excludes speech finalization, orchestration gaps, transport, browser rendering, and optional Groq synthesis.
        </span>
        <span className="flex shrink-0 flex-wrap items-center gap-2">
          {summary.totalAfterFinalInputMs !== null && (
            <span
              title="Canonical backend-measured full time after final input; network and browser rendering excluded"
              className="rounded-full border border-white/10 bg-white/5 px-2 py-1 font-mono text-slate-300"
            >
              Full request {formatResponseLatency(summary.totalAfterFinalInputMs)}
            </span>
          )}
          <a
            href="/evidence"
            className="inline-flex items-center gap-1 font-semibold text-cyan-300 hover:text-cyan-200"
          >
            Full latency evidence <ArrowSquareOut size={11} />
          </a>
        </span>
      </div>
    </aside>
  );
};
