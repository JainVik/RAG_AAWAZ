import React from 'react';
import { Stack, CheckCircle, Info } from '@phosphor-icons/react';
import type { ChunkRepresentation } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface ChunkRepresentationsCardProps {
  representations: ChunkRepresentation[];
}

export const ChunkRepresentationsCard: React.FC<ChunkRepresentationsCardProps> = ({
  representations,
}) => {
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
              Chunk Representation Specifications
            </h2>
            <p className="text-xs text-slate-400">
              {representations.length} measured multi-strategy representation{representations.length === 1 ? '' : 's'} in the active index manifest
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
          <Info size={14} className="text-cyan-400" />
          <span>Automated runtime routing • No manual selection</span>
        </div>
      </div>

      {/* Comparison Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {representations.map((rep) => (
          <div
            key={rep.strategy}
            className="p-4 bg-white/5 border border-white/8 hover:border-purple-400/30 rounded-xl flex flex-col justify-between space-y-3 transition-colors"
          >
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-white tracking-tight">{rep.name}</span>
                <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${rep.enabled ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20' : 'bg-slate-500/10 text-slate-400 border-white/10'}`}>
                  <CheckCircle size={11} weight="fill" />
                  <span>{rep.enabled ? 'ACTIVE' : 'DISABLED'}</span>
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed font-sans">{rep.description}</p>
            </div>

            <div className="pt-3 border-t border-white/10 grid grid-cols-2 sm:grid-cols-4 gap-1 text-center font-mono">
              <div className="p-1.5 bg-black/20 rounded-lg">
                <span className="block text-[9px] uppercase text-slate-500 font-sans">Points</span>
                <span className="text-xs font-bold text-cyan-300 font-mono-tabular">
                  {rep.chunk_count.toLocaleString()}
                </span>
              </div>
              <div className="p-1.5 bg-black/20 rounded-lg">
                <span className="block text-[9px] uppercase text-slate-500 font-sans">Avg Len</span>
                <span className="text-xs font-bold text-white font-mono-tabular">
                  {rep.avg_text_length} ch
                </span>
              </div>
              <div className="p-1.5 bg-black/20 rounded-lg">
                <span className="block text-[9px] uppercase text-slate-500 font-sans">Size</span>
                <span className="text-xs font-bold text-slate-300 font-mono-tabular">
                  {(rep.artifact_bytes / (1024 * 1024)).toFixed(1)} MB
                </span>
              </div>
              <div className="p-1.5 bg-black/20 rounded-lg">
                <span className="block text-[9px] uppercase text-slate-500 font-sans">Build</span>
                <span className="text-xs font-bold text-slate-300 font-mono-tabular">
                  {rep.build_duration_seconds.toFixed(2)} s
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </GlassSurface>
  );
};
