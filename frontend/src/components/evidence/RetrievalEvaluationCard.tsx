import React, { useState } from 'react';
import {
  CaretDown,
  ChartLineUp,
  CheckCircle,
  Clock,
  Info,
  ShieldCheck,
} from '@phosphor-icons/react';
import type { RetrievalMetrics } from '../../types/api';

interface RetrievalEvaluationCardProps {
  metrics: RetrievalMetrics;
}

export const RetrievalEvaluationCard: React.FC<RetrievalEvaluationCardProps> = ({ metrics }) => {
  const [openMetricHelp, setOpenMetricHelp] = useState<string | null>(null);
  const percent = (value: number | null) =>
    value === null ? 'Not measured' : `${(value * 100).toFixed(2)}%`;
  const latency = (value: number | null) =>
    value === null ? 'Not measured' : `${value.toFixed(1)} ms`;
  const isPostHocRegression = metrics.failed_checks.includes(
    'fresh_untouched_final_evaluation',
  );
  const metricItems = [
    { label: 'Recall@1', value: percent(metrics.recall_at_1), desc: 'Relevant passage appears at rank 1' },
    { label: 'Recall@5', value: percent(metrics.recall_at_5), desc: 'Relevant passage appears in the top 5' },
    { label: 'Recall@10', value: percent(metrics.recall_at_10), desc: 'Relevant passage appears in the top 10' },
    { label: 'MRR@10', value: percent(metrics.mrr_at_10), desc: 'Mean reciprocal rank across retained queries' },
    { label: 'nDCG@10', value: percent(metrics.ndcg_at_10), desc: 'Ranking quality within the top 10' },
  ];

  return (
    <article className="refractive-glass-card space-y-6 p-6 transition-all hover:border-blue-500/30 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/10 dark:border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-blue-400/20 bg-blue-500/10 p-2.5 text-blue-600 dark:text-blue-400">
            <ChartLineUp size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base font-bold tracking-tight text-black dark:text-white sm:text-lg">
              {metrics.qualifying
                ? 'Final held-out retrieval evaluation'
                : isPostHocRegression
                  ? 'Retrieval regression evaluation'
                  : 'Retrieval evaluation'}
            </h2>
            <p className="text-xs text-black dark:text-slate-400">
              {metrics.sample_count} retained queries · {metrics.failure_count} failures ·{' '}
              {percent(metrics.completion_coverage)} completion
            </p>
          </div>
        </div>

        {metrics.qualifying ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
            <ShieldCheck size={14} weight="fill" className="text-emerald-600 dark:text-emerald-400" />
            Qualifying held-out report
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-800 dark:text-amber-300">
            <Info size={14} />{' '}
            {isPostHocRegression ? 'Non-qualifying regression evidence' : 'Non-qualifying'}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {metricItems.map((metric) => (
          <div
            key={metric.label}
            className="space-y-1 rounded-xl border border-black/10 dark:border-white/8 bg-black/[0.03] dark:bg-white/5 p-4 transition-colors hover:border-blue-400/30"
          >
            <div className="flex items-center justify-between text-xs font-semibold text-black dark:text-slate-400">
              <span>{metric.label}</span>
              <button
                type="button"
                aria-label={`Explain ${metric.label}`}
                aria-expanded={openMetricHelp === metric.label}
                onClick={() =>
                  setOpenMetricHelp((current) =>
                    current === metric.label ? null : metric.label,
                  )
                }
                onBlur={() => setOpenMetricHelp(null)}
                className="group relative rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 cursor-pointer"
              >
                <Info size={13} className="text-slate-500 group-hover:text-black dark:group-hover:text-slate-300" />
                <span
                  className={`${
                    openMetricHelp === metric.label ? 'block' : 'hidden group-hover:block'
                  } pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-48 -translate-x-1/2 rounded-lg border border-black/10 dark:border-white/15 bg-white dark:bg-slate-900 p-2 text-[10px] text-black dark:text-slate-200 shadow-xl`}
                >
                  {metric.desc}
                </span>
              </button>
            </div>
            <div className="font-mono text-xl font-bold text-blue-600 dark:text-blue-300 sm:text-2xl">
              {metric.value}
            </div>
          </div>
        ))}
      </div>

      {!metrics.qualifying && metrics.failed_checks.length > 0 && (
        <div className="glass-inner-box px-4 py-3 text-xs text-amber-800 dark:text-amber-200">
          Qualification pending: {metrics.failed_checks.join(', ').replaceAll('_', ' ')}
        </div>
      )}

      <details className="glass-inner-box overflow-hidden">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-semibold text-black dark:text-slate-300">
          <span className="inline-flex items-center gap-2">
            <Clock size={16} className="text-blue-600 dark:text-blue-400" />
            Evaluator details · direct-index latency and provenance
          </span>
          <CaretDown size={16} className="text-slate-400" />
        </summary>
        <div className="space-y-4 border-t border-black/10 dark:border-white/8 pt-4 mt-3">
          <p className="text-[10px] text-black dark:text-slate-400">
            Direct retrieval evaluation ({metrics.direct_latency_sample_count ?? 0} rows). This is
            distinct from end-to-end voice latency.
          </p>
          <div className="grid grid-cols-2 gap-2.5 text-center sm:grid-cols-4">
            {[
              ['P50', metrics.direct_p50_ms],
              ['P70', metrics.direct_p70_ms],
              ['P95', metrics.direct_p95_ms],
              ['Maximum', metrics.direct_max_ms],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-lg border border-black/5 dark:border-white/5 bg-black/5 dark:bg-white/5 p-2.5">
                <span className="block text-[10px] font-bold uppercase text-black dark:text-slate-400">{label}</span>
                <span className="font-mono text-sm font-bold text-black dark:text-white">
                  {latency(value as number | null)}
                </span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-3">
            <div className="flex items-center justify-between rounded-xl border border-black/10 dark:border-white/8 bg-black/[0.03] dark:bg-white/5 p-3">
              <span className="text-black dark:text-slate-400">Hit coverage</span>
              <span className="font-mono font-bold text-black dark:text-white">{percent(metrics.retrieval_hit_coverage)}</span>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-black/10 dark:border-white/8 bg-black/[0.03] dark:bg-white/5 p-3">
              <span className="text-black dark:text-slate-400">Execution failures</span>
              <span className="flex items-center gap-1 font-mono font-bold text-emerald-600 dark:text-emerald-400">
                <CheckCircle size={14} weight="fill" /> {metrics.failure_count}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-black/10 dark:border-white/8 bg-black/[0.03] dark:bg-white/5 p-3">
              <span className="text-black dark:text-slate-400">Split provenance</span>
              <span className="font-mono font-bold text-blue-600 dark:text-blue-300">
                {metrics.split_verified ? 'Verified' : 'Unverified'}
              </span>
            </div>
          </div>
        </div>
      </details>
    </article>
  );
};
