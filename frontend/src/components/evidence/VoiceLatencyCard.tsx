import React from 'react';
import {
  CaretDown,
  CheckCircle,
  HourglassSimple,
  Info,
  Lightning,
  Timer,
} from '@phosphor-icons/react';
import type { VoiceLatencyReport } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface VoiceLatencyCardProps {
  latency: VoiceLatencyReport;
}

function formatLatency(value: number | null): string {
  return value === null ? 'Not measured' : `${value.toFixed(1)} ms`;
}

function TimingSummary({
  title,
  p50,
  p95,
  maximum,
}: {
  title: string;
  p50: number | null;
  p95: number | null;
  maximum: number | null;
}) {
  return (
    <div className="space-y-3 rounded-xl border border-white/8 bg-white/5 p-4">
      <span className="block text-xs font-bold text-cyan-300">{title}</span>
      <div className="grid grid-cols-3 gap-2 text-center font-mono">
        {[['P50', p50], ['P95', p95], ['MAX', maximum]].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg bg-black/20 p-2">
            <span className="block text-[9px] font-sans text-slate-500">{label}</span>
            <span className="text-xs font-bold text-white">{formatLatency(value as number | null)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export const VoiceLatencyCard: React.FC<VoiceLatencyCardProps> = ({ latency }) => {
  const isPending = !latency.qualifying || latency.sample_count === 0;

  return (
    <GlassSurface
      borderRadius={20}
      brightness={35}
      opacity={0.85}
      className="space-y-6 p-6 transition-all hover:border-cyan-500/30 sm:p-8"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <div className={`rounded-xl border p-2.5 ${isPending ? 'border-amber-400/20 bg-amber-500/10 text-amber-400' : 'border-emerald-400/20 bg-emerald-500/10 text-emerald-400'}`}>
            <Timer size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base font-bold tracking-tight text-white sm:text-lg">
              Post-final-audio voice latency
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Audited real-provider speech-to-grounded-answer benchmark
            </p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${isPending ? 'border-slate-500/30 bg-white/5 text-slate-300' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'}`}>
          {isPending ? <HourglassSimple size={14} /> : <Lightning size={14} weight="fill" />}
          {isPending ? 'Not measured' : 'Qualifying report'}
        </span>
      </div>

      {isPending ? (
        <>
          <div className="grid gap-3 sm:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
            <div className="rounded-xl border border-white/8 bg-white/5 p-4">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Measured rows</span>
              <p className="mt-1 font-mono text-3xl font-bold text-white">{latency.sample_count}</p>
            </div>
            <div className="flex gap-2 rounded-xl border border-cyan-400/15 bg-cyan-500/5 p-4 text-xs leading-relaxed text-slate-400">
              <Info size={17} className="shrink-0 text-cyan-400" />
              <span>No aggregate voice percentile is shown until the cold/warm, multilingual, transcript-match, timing-coverage, and zero-failure checks pass.</span>
            </div>
          </div>
          <details className="overflow-hidden rounded-xl border border-white/8 bg-black/15">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-bold text-slate-200">
              <span>Evaluator details · pending qualification criteria</span>
              <CaretDown size={15} className="text-slate-500" />
            </summary>
            <div className="grid grid-cols-1 gap-2.5 border-t border-white/8 p-4 sm:grid-cols-2">
              {latency.pending_criteria.map((criterion) => (
                <div key={criterion} className="flex items-start gap-2.5 rounded-xl border border-white/8 bg-white/5 p-3 text-xs text-slate-300">
                  <CheckCircle size={16} weight="fill" className="mt-0.5 shrink-0 text-cyan-400" />
                  <span className="leading-relaxed">{criterion}</span>
                </div>
              ))}
            </div>
          </details>
        </>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TimingSummary title="Cold start" p50={latency.cold_p50_ms} p95={latency.cold_p95_ms} maximum={latency.cold_p100_ms} />
            <TimingSummary title="Warm runtime" p50={latency.warm_p50_ms} p95={latency.warm_p95_ms} maximum={latency.warm_p100_ms} />
          </div>
          <details className="rounded-xl border border-white/8 bg-black/15 px-4 py-3 text-xs text-slate-400">
            <summary className="cursor-pointer font-bold text-slate-200">Evaluator details · P70</summary>
            <div className="mt-3 grid grid-cols-2 gap-3 border-t border-white/8 pt-3 font-mono">
              <span>Cold P70: {formatLatency(latency.cold_p70_ms)}</span>
              <span>Warm P70: {formatLatency(latency.warm_p70_ms)}</span>
            </div>
          </details>
        </>
      )}
    </GlassSurface>
  );
};
