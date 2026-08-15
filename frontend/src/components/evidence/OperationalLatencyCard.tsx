import React from 'react';
import { ChartLine, ClockCounterClockwise, Info, Lightning } from '@phosphor-icons/react';
import type { OperationalMetrics, StageLatencyPercentiles } from '../../types/api';
import { formatStageLatency } from '../../utils/pipelineLatency';
import GlassSurface from '../ui/GlassSurface';

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
    ['MAX', values?.p100],
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {cells.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-white/8 bg-white/5 p-3 text-center">
          <span className="block text-[9px] font-bold uppercase tracking-wider text-slate-500">{label}</span>
          <span className="mt-1 block font-mono text-lg font-bold text-white">
            {value === undefined ? 'Not measured' : formatStageLatency(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function StageRow({ label, scope, values }: { label: string; scope?: string; values: StageLatencyPercentiles }) {
  return (
    <div className="grid grid-cols-[minmax(9rem,1.5fr)_repeat(4,minmax(4.2rem,0.7fr))] items-center gap-2 border-t border-white/6 px-3 py-2.5 text-[10px] first:border-t-0">
      <div className="min-w-0">
        <span className="block truncate font-semibold text-slate-200">{label}</span>
        <span className="text-[9px] text-slate-500">{values.count} samples{scope ? ` · ${scope}` : ''}</span>
      </div>
      {[values.p50, values.p70, values.p95, values.p100].map((value, index) => (
        <span key={index} className="text-right font-mono text-slate-300">
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
    <GlassSurface borderRadius={20} brightness={35} opacity={0.85} className="space-y-5 p-6 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 pb-4">
        <div className="flex items-start gap-3">
          <span className="rounded-xl border border-cyan-400/20 bg-cyan-500/10 p-2.5 text-cyan-300">
            <Lightning size={22} weight="fill" />
          </span>
          <div>
            <h2 className="text-base font-bold text-white sm:text-lg">Live process performance</h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Full post-final-input response and internal stage percentiles
            </p>
          </div>
        </div>
        <span className="rounded-full border border-amber-400/25 bg-amber-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-200">
          Operational · non-qualifying
        </span>
      </div>

      <div className="flex gap-2 rounded-xl border border-cyan-400/15 bg-cyan-500/5 p-3 text-[10px] leading-relaxed text-slate-400">
        <Info size={15} className="shrink-0 text-cyan-400" />
        <span>Current backend process · primary text and voice outcomes combined, including abstentions and errors · resets whenever the backend restarts. Formal benchmark evidence remains separate below.</span>
      </div>

      {metrics?.latency_ms ? (
        <>
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-bold text-slate-200">
                <ChartLine size={15} className="text-cyan-400" /> Overall primary response
              </p>
              <p className="mt-1 text-[10px] text-slate-500">{metrics.latency_sample_count} timed responses from {metrics.requests_total} process requests</p>
            </div>
          </div>
          <PercentileGrid values={metrics.latency_ms} />

          {rows.length > 0 && (
            <details open className="overflow-x-auto rounded-xl border border-white/8 bg-black/15">
              <summary className="cursor-pointer px-3 py-3 text-xs font-bold text-slate-200">
                Detailed stage percentiles
              </summary>
              <div className="min-w-[620px]">
                <div className="grid grid-cols-[minmax(9rem,1.5fr)_repeat(4,minmax(4.2rem,0.7fr))] gap-2 border-t border-white/8 px-3 py-2 text-[9px] font-bold uppercase tracking-wider text-slate-500">
                  <span>Stage</span><span className="text-right">P50</span><span className="text-right">P70</span><span className="text-right">P95</span><span className="text-right">Max</span>
                </div>
                {rows.map((row) => (
                  <StageRow key={row.key} label={row.label} scope={row.scope} values={row.values} />
                ))}
                <p className="border-t border-white/8 px-3 py-2 text-[9px] text-slate-500">
                  Each row is its own measured distribution. Percentile rows are not additive and are never used to reconstruct the overall total.
                </p>
              </div>
            </details>
          )}

          {metrics.groq_synthesis.latency_ms && (
            <div className="rounded-xl border border-violet-400/15 bg-violet-500/5 p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-violet-200">Optional Groq synthesis</span>
                <span className="text-[9px] text-slate-500">{metrics.groq_synthesis.latency_sample_count} samples · measured separately</span>
              </div>
              <PercentileGrid values={metrics.groq_synthesis.latency_ms} />
            </div>
          )}
        </>
      ) : (
        <div className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/5 p-5 text-sm text-slate-300">
          <ClockCounterClockwise size={20} className="shrink-0 text-slate-500" />
          <div>
            <p className="font-semibold">Live timing is not available yet</p>
            <p className="mt-1 text-xs text-slate-500">{error ?? 'Run a text or voice query to create process-local timing samples.'}</p>
          </div>
        </div>
      )}
    </GlassSurface>
  );
};
