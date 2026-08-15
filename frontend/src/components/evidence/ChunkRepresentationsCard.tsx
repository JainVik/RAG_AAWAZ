import React from 'react';
import { Stack, CheckCircle, Info, CaretDown } from '@phosphor-icons/react';
import type { ChunkRepresentation } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface ChunkRepresentationsCardProps {
  representations: ChunkRepresentation[];
}

export const ChunkRepresentationsCard: React.FC<ChunkRepresentationsCardProps> = ({
  representations,
}) => {
  const totalPoints = representations.reduce((sum, representation) => sum + representation.chunk_count, 0);
  const segmentTones = ['bg-cyan-400', 'bg-blue-400', 'bg-violet-400', 'bg-fuchsia-400', 'bg-emerald-400'];

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
          <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-400/20 text-purple-400">
            <Stack size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
              Five retrieval representations
            </h2>
            <p className="text-xs text-slate-400">
              {totalPoints.toLocaleString()} indexed points distributed across {representations.length} active representation types
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
          <Info size={14} className="text-cyan-400" />
          <span>Automated runtime routing • No manual selection</span>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex h-3 overflow-hidden rounded-full bg-white/5" aria-label="Indexed point distribution by representation">
          {representations.map((representation, index) => (
            <span
              key={representation.strategy}
              title={`${representation.name}: ${representation.chunk_count.toLocaleString()} points`}
              className={segmentTones[index % segmentTones.length]}
              style={{ width: `${totalPoints > 0 ? (representation.chunk_count / totalPoints) * 100 : 0}%` }}
            />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {representations.map((representation, index) => (
            <div key={representation.strategy} className="rounded-xl border border-white/8 bg-white/5 p-3">
              <span className={`mb-2 block h-1.5 w-8 rounded-full ${segmentTones[index % segmentTones.length]}`} />
              <p className="truncate text-[10px] font-semibold text-slate-300" title={representation.name}>{representation.name}</p>
              <p className="mt-1 font-mono text-sm font-bold text-white">{representation.chunk_count.toLocaleString()}</p>
            </div>
          ))}
        </div>

        <details className="overflow-hidden rounded-xl border border-white/8 bg-black/15">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-bold text-slate-200">
            <span>Evaluator details · representation construction and footprint</span>
            <CaretDown size={15} className="text-slate-500" />
          </summary>
          <div className="grid grid-cols-1 gap-3 border-t border-white/8 p-4 md:grid-cols-2 lg:grid-cols-3">
            {representations.map((rep) => (
              <div key={rep.strategy} className="flex flex-col justify-between space-y-3 rounded-xl border border-white/8 bg-white/5 p-4">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-white">{rep.name}</span>
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${rep.enabled ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300' : 'border-white/10 bg-slate-500/10 text-slate-400'}`}>
                      <CheckCircle size={11} weight="fill" /> {rep.enabled ? 'ACTIVE' : 'DISABLED'}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-slate-400">{rep.description}</p>
                </div>
                <div className="grid grid-cols-3 gap-1 border-t border-white/10 pt-3 text-center font-mono">
                  <div className="rounded-lg bg-black/20 p-1.5"><span className="block text-[9px] uppercase text-slate-500">Avg chars</span><span className="text-xs font-bold text-white">{rep.avg_text_length}</span></div>
                  <div className="rounded-lg bg-black/20 p-1.5"><span className="block text-[9px] uppercase text-slate-500">Artifact</span><span className="text-xs font-bold text-slate-300">{(rep.artifact_bytes / (1024 * 1024)).toFixed(1)} MB</span></div>
                  <div className="rounded-lg bg-black/20 p-1.5"><span className="block text-[9px] uppercase text-slate-500">Build</span><span className="text-xs font-bold text-slate-300">{rep.build_duration_seconds.toFixed(2)} s</span></div>
                </div>
              </div>
            ))}
          </div>
        </details>
      </div>
    </GlassSurface>
  );
};
