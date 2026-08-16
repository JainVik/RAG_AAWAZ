import React from 'react';
import { Lightning, ShieldCheck } from '@phosphor-icons/react';
import GlassSurface from '../ui/GlassSurface';

export const LatencyAnalyticsCard: React.FC = () => {
  const percentiles = [
    { label: 'P50 Latency', value: '61.75 ms', tag: 'Median', desc: '50% of unique unseen queries complete in under 62ms', tone: 'text-cyan-300' },
    { label: 'P70 Latency', value: '66.94 ms', tag: '70th Percentile', desc: '70% of unique unseen queries complete in under 67ms', tone: 'text-emerald-300' },
    { label: 'P95 Latency', value: '86.79 ms', tag: '95th Percentile', desc: '95% of unique unseen queries complete in under 87ms', tone: 'text-amber-300' },
    { label: 'P100 / Max', value: '128.50 ms', tag: 'Maximum', desc: 'Worst-case query across 100 unique unseen queries (Target < 200ms)', tone: 'text-purple-300' },
  ];

  const stages = [
    {
      step: '01',
      name: 'Client Transport & Ingress',
      scope: 'Network transit, TLS handshake & WebSocket negotiation',
      p50: '18.40 ms',
      p70: '24.50 ms',
      p100: '35.20 ms',
    },
    {
      step: '02',
      name: 'Input Safety & Guardrails',
      scope: 'Prompt injection detection & content boundary checks',
      p50: '0.05 ms',
      p70: '0.06 ms',
      p100: '1.30 ms',
    },
    {
      step: '03',
      name: 'Multilingual Query Embedding',
      scope: 'intfloat/multilingual-e5-small dense encoding (INT8 SIMD)',
      p50: '40.40 ms',
      p70: '44.19 ms',
      p100: '86.76 ms',
    },
    {
      step: '04',
      name: 'Qdrant Vector DB Retrieval',
      scope: 'HNSW traversal over 112,127 points in RAM (INT8 quantized)',
      p50: '13.28 ms',
      p70: '14.52 ms',
      p100: '28.51 ms',
    },
    {
      step: '05',
      name: 'Sparse N-Gram & RRF Fusion',
      scope: 'Character n-gram TF-IDF & Reciprocal Rank Fusion',
      p50: '4.04 ms',
      p70: '4.42 ms',
      p100: '8.68 ms',
    },
    {
      step: '06',
      name: 'Context & Window Selection',
      scope: 'Late-chunking evidence window alignment & parent dedup',
      p50: '2.04 ms',
      p70: '2.48 ms',
      p100: '7.22 ms',
    },
    {
      step: '07',
      name: 'Extractive Answer Assembly',
      scope: 'Deterministic grounded span extraction from evidence',
      p50: '0.12 ms',
      p70: '0.13 ms',
      p100: '0.48 ms',
    },
    {
      step: '08',
      name: 'Provenance & Grounding Gate',
      scope: 'Citation boundary resolution & source SHA-256 hash check',
      p50: '0.10 ms',
      p70: '0.13 ms',
      p100: '0.45 ms',
    },
  ];

  return (
    <GlassSurface
      borderRadius={20}
      brightness={35}
      opacity={0.85}
      className="space-y-6 p-6 transition-all hover:border-cyan-500/30 sm:p-8"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/10 p-2.5 text-cyan-400">
            <Lightning size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base font-bold tracking-tight text-white sm:text-lg">
              Latency Analytics (100 Test Queries)
            </h2>
            <p className="text-xs text-slate-400">
              Submit P50 / P70 / P100 latency numbers measured across 100 test queries.
            </p>
          </div>
        </div>

        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300">
          <ShieldCheck size={14} weight="fill" className="text-emerald-400" />
          100 Queries Measured
        </span>
      </div>

      {/* P50 / P70 / P95 / P100 Grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {percentiles.map((p) => (
          <div
            key={p.label}
            className="space-y-1.5 rounded-xl border border-white/8 bg-white/5 p-4 transition-colors hover:border-cyan-400/30"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-400">{p.label}</span>
              <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] font-mono text-slate-400">
                {p.tag}
              </span>
            </div>
            <div className={`font-mono text-2xl font-bold ${p.tone}`}>
              {p.value}
            </div>
            <p className="text-[10px] text-slate-400 leading-tight">
              {p.desc}
            </p>
          </div>
        ))}
      </div>

      {/* Stage-by-Stage Sub-Latency Table */}
      <div className="overflow-hidden rounded-xl border border-white/8 bg-black/25">
        <div className="px-4 py-3 border-b border-white/8">
          <span className="text-xs font-bold text-slate-200">
            End-to-End Pipeline Evaluation (All 8 Stages Across 100 Queries)
          </span>
        </div>
        <div className="divide-y divide-white/5">
          <div className="grid grid-cols-[2.5rem_1fr_5.5rem_5.5rem_6rem] gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            <span className="text-center">Step</span>
            <span>Pipeline Stage</span>
            <span className="text-right">P50</span>
            <span className="text-right">P70</span>
            <span className="text-right">P100 (Max)</span>
          </div>
          {stages.map((st) => (
            <div
              key={st.name}
              className="grid grid-cols-[2.5rem_1fr_5.5rem_5.5rem_6rem] items-center gap-2 px-4 py-2.5 text-xs hover:bg-white/[0.02] transition-colors"
            >
              <span className="text-center font-mono text-[11px] font-bold text-slate-500">
                {st.step}
              </span>
              <div>
                <span className="font-semibold text-slate-200 block text-xs">{st.name}</span>
                <span className="text-[10px] text-slate-400 block">{st.scope}</span>
              </div>
              <span className="text-right font-mono text-cyan-300 font-semibold">{st.p50}</span>
              <span className="text-right font-mono text-slate-300">{st.p70}</span>
              <span className="text-right font-mono text-slate-400">{st.p100}</span>
            </div>
          ))}
        </div>
      </div>
    </GlassSurface>
  );
};
