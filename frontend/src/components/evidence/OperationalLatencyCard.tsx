import React from 'react';
import { ChartLine, ClockCounterClockwise, Info, Lightning } from '@phosphor-icons/react';
import type { OperationalMetrics, StageLatencyPercentiles } from '../../types/api';
import { formatStageLatency } from '../../utils/pipelineLatency';

interface OperationalLatencyCardProps {
  metrics: OperationalMetrics | null;
  error?: string | null;
}

const STAGES: ReadonlyArray<{ key: string; label: string; scope?: string }> = [
  { key: 'audio_start_to_final_response', label: 'Audio start → final response', scope: 'voice; includes speaking time' },
  { key: 'stt_first_partial_from_audio_start', label: 'First live transcript', scope: 'voice; from audio start' },
  { key: 'stt_finalize', label: 'Speech finalization', scope: 'voice only' },
  { key: 'stt_last_final_after_end', label: 'Last final transcript', scope: 'voice; after end marker' },
  { key: 'input_guarded', label: 'Input safety' },
  { key: 'retrieved', label: 'Embedding + hybrid retrieval' },
  { key: 'evidence_selected', label: 'Evidence selection' },
  { key: 'answered', label: 'Answer extraction' },
  { key: 'verified', label: 'Grounding verification' },
  { key: 'serialization', label: 'Response serialization', scope: 'voice transport' },
];

function PercentileGrid({ values }: { values: OperationalMetrics['latency_ms'] }) {
  const cells = [
    ['P50', values?.p50],
    ['P70', values?.p70],
    ['P95', values?.p95],
    ['P100 / MAX', values?.p100],
  ] as const;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
      {cells.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-black/10 dark:border-white/8 bg-black/[0.03] dark:bg-white/5 p-3.5 text-center">
          <span className="block text-[9px] font-bold uppercase tracking-wider text-black dark:text-slate-500">{label}</span>
          <span className="mt-1 block font-mono text-lg font-bold text-blue-600 dark:text-blue-300">
            {value === undefined ? 'Not measured' : formatStageLatency(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function StageRow({ label, scope, values }: { label: string; scope?: string; values: StageLatencyPercentiles }) {
  return (
    <div className="grid grid-cols-[minmax(9rem,1.5fr)_repeat(4,minmax(4.2rem,0.7fr))] items-center gap-2 border-t border-black/5 dark:border-white/6 px-3 py-2.5 text-[10px] first:border-t-0">
      <div className="min-w-0">
        <span className="block truncate font-semibold text-black dark:text-slate-200">{label}</span>
        <span className="text-[9px] text-black dark:text-slate-500">{values.count} samples{scope ? ` · ${scope}` : ''}</span>
      </div>
      {[values.p50, values.p70, values.p95, values.p100].map((value, index) => (
        <span key={index} className="text-right font-mono text-black dark:text-slate-300 font-medium">
          {formatStageLatency(value)}
        </span>
      ))}
    </div>
  );
}

export const OperationalLatencyCard: React.FC<OperationalLatencyCardProps> = ({ metrics, error }) => {
  const rows = metrics
    ? STAGES.flatMap((stage) => {
        const values = metrics.timings_ms[stage.key];
        return values ? [{ ...stage, values }] : [];
      })
    : [];

  return (
    <article className="refractive-glass-card refractive-glass-card-primary space-y-5 p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/10 dark:border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-blue-400/30 bg-blue-500/10 dark:bg-blue-500/15 p-2.5 text-blue-600 dark:text-blue-300">
            <Lightning size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base font-bold text-black dark:text-white sm:text-lg">Live process performance</h2>
            <p className="mt-0.5 text-xs text-black dark:text-slate-400">
              Full post-final-input response and internal stage percentiles
            </p>
          </div>
        </div>
        <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 font-mono text-xs font-semibold text-blue-700 dark:text-blue-200">
          Operational · non-qualifying
        </span>
      </div>

      <div className="glass-inner-box flex gap-2 text-[10px] leading-relaxed text-black dark:text-slate-300">
        <Info size={15} className="shrink-0 text-blue-600 dark:text-blue-400" />
        <span>Current backend process · primary text and voice outcomes combined, including abstentions and errors · resets whenever the backend restarts. Formal benchmark evidence remains separate below.</span>
      </div>

      {metrics?.latency_ms ? (
        <>
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-bold text-black dark:text-slate-200">
                <ChartLine size={15} className="text-blue-600 dark:text-blue-400" /> Overall primary response
              </p>
              <p className="mt-1 text-[10px] text-black dark:text-slate-400">{metrics.latency_sample_count} timed responses from {metrics.requests_total} process requests</p>
            </div>
          </div>
          <PercentileGrid values={metrics.latency_ms} />

          {rows.length > 0 && (
            <details className="glass-inner-box overflow-x-auto">
              <summary className="cursor-pointer text-xs font-bold text-black dark:text-slate-200">
                Evaluator details · P50 / P70 / P95 / maximum by stage
              </summary>
              <div className="mt-3 min-w-[620px]">
                <div className="grid grid-cols-[minmax(9rem,1.5fr)_repeat(4,minmax(4.2rem,0.7fr))] gap-2 border-t border-black/10 dark:border-white/10 pt-2 text-[9px] font-bold uppercase tracking-wider text-black dark:text-slate-400">
                  <span>Stage</span><span className="text-right">P50</span><span className="text-right">P70</span><span className="text-right">P95</span><span className="text-right">Max</span>
                </div>
                {rows.map((row) => (
                  <StageRow key={row.key} label={row.label} scope={row.scope} values={row.values} />
                ))}
                <p className="border-t border-black/10 dark:border-white/10 pt-2 text-[9px] text-black dark:text-slate-400">
                  Each row is its own measured distribution. Percentile rows are not additive and are never used to reconstruct the overall total.
                </p>
              </div>
            </details>
          )}

          {metrics.groq_synthesis.latency_ms && (
            <div className="rounded-xl border border-violet-500/30 bg-violet-500/10 p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-violet-900 dark:text-violet-200">Optional Groq synthesis</span>
                <span className="text-[9px] text-black dark:text-slate-400">{metrics.groq_synthesis.latency_sample_count} samples · measured separately</span>
              </div>
              <PercentileGrid values={metrics.groq_synthesis.latency_ms} />
            </div>
          )}
        </>
      ) : (
        <div className="flex items-center gap-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.03] dark:bg-white/[0.04] p-5 text-sm text-black dark:text-slate-300">
          <ClockCounterClockwise size={20} className="shrink-0 text-slate-400" />
          <div>
            <p className="font-semibold text-black dark:text-white">Live timing is not available yet</p>
            <p className="mt-1 text-xs text-black dark:text-slate-400">{error ?? 'Run a text or voice query to create process-local timing samples.'}</p>
          </div>
        </div>
      )}
    </article>
  );
};
