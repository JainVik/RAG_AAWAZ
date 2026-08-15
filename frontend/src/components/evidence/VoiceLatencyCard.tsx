import React from 'react';
import { Timer, HourglassSimple, Lightning, Info, CheckCircle } from '@phosphor-icons/react';
import type { VoiceLatencyReport } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface VoiceLatencyCardProps {
  latency: VoiceLatencyReport;
}

export const VoiceLatencyCard: React.FC<VoiceLatencyCardProps> = ({ latency }) => {
  const isPending = !latency.qualifying || latency.sample_count === 0;

  const criteria = latency.pending_criteria || [
    'Prescribed sample count across human and synthetic multilingual audio',
    'Supported language mixes across varied noise conditions and duration classes',
    'Cold and warm operation timing breakdown with canonical stage coverage',
    'Full transcript matching, completed/evidence responses, and zero request failures',
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
          <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-400/20 text-amber-400">
            <Timer size={22} weight="bold" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Post-Final-Audio Voice Latency
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                Pending qualifying run
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Real-provider end-to-end speech-to-grounded-answer benchmark
            </p>
          </div>
        </div>

        {isPending ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-500/10 text-amber-300 border border-amber-500/30 rounded-full text-xs font-semibold">
            <HourglassSimple size={14} className="animate-spin" />
            <span>Qualifying Voice Latency Run Pending</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 rounded-full text-xs font-semibold">
            <Lightning size={14} weight="fill" className="text-emerald-400" />
            <span>Live Provider Validated</span>
          </span>
        )}
      </div>

      {isPending ? (
        <div className="space-y-4">
          <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
              <Info size={16} className="text-cyan-400 shrink-0" />
              <span>Truthful Benchmarking Policy</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              In accordance with strict evaluation rules, single request timings are never presented as aggregate percentiles (P50, P70, P95, P100), nor are ungrounded &ldquo;&lt;200ms&rdquo; SLA claims made. A qualifying voice report requires an audited multi-condition run.
            </p>
          </div>

          <div className="space-y-2.5">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
              Required Qualifying Criteria for Final Voice Report
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {criteria.map((c, idx) => (
                <div key={idx} className="p-3 bg-white/5 border border-white/8 rounded-xl flex items-start gap-2.5 text-xs text-slate-300">
                  <CheckCircle size={16} weight="fill" className="text-cyan-400 shrink-0 mt-0.5" />
                  <span className="leading-relaxed">{c}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Cold Runs */}
          <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-2">
            <span className="text-xs font-bold text-cyan-300 block">Cold Start Runs</span>
            <div className="grid grid-cols-4 gap-1 text-center font-mono">
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P50</span>
                <span className="text-xs font-bold text-white">{latency.cold_p50_ms}ms</span>
              </div>
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P70</span>
                <span className="text-xs font-bold text-white">{latency.cold_p70_ms}ms</span>
              </div>
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P95</span>
                <span className="text-xs font-bold text-white">{latency.cold_p95_ms}ms</span>
              </div>
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P100</span>
                <span className="text-xs font-bold text-white">{latency.cold_p100_ms}ms</span>
              </div>
            </div>
          </div>

          {/* Warm Runs */}
          <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-2">
            <span className="text-xs font-bold text-cyan-300 block">Warm Runtime Runs</span>
            <div className="grid grid-cols-4 gap-1 text-center font-mono">
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P50</span>
                <span className="text-xs font-bold text-emerald-400">{latency.warm_p50_ms}ms</span>
              </div>
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P70</span>
                <span className="text-xs font-bold text-emerald-400">{latency.warm_p70_ms}ms</span>
              </div>
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P95</span>
                <span className="text-xs font-bold text-emerald-400">{latency.warm_p95_ms}ms</span>
              </div>
              <div className="p-2 bg-black/20 rounded-lg">
                <span className="text-[9px] text-slate-400 block font-sans">P100</span>
                <span className="text-xs font-bold text-emerald-400">{latency.warm_p100_ms}ms</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </GlassSurface>
  );
};
