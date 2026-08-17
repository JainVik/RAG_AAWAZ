import React from 'react';
import { Stack, CheckCircle, Info } from '@phosphor-icons/react';
import type { ChunkRepresentation } from '../../types/api';

interface ChunkRepresentationsCardProps {
  representations: ChunkRepresentation[];
}

export const ChunkRepresentationsCard: React.FC<ChunkRepresentationsCardProps> = ({
  representations,
}) => {
  const totalPoints = representations.reduce((sum, representation) => sum + representation.chunk_count, 0);
  const segmentTones = ['bg-blue-600', 'bg-blue-500', 'bg-blue-400', 'bg-indigo-500', 'bg-indigo-400'];

  return (
    <article className="refractive-glass-card refractive-glass-card-primary p-6 sm:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-black/10 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-blue-500/10 dark:bg-blue-500/15 border border-blue-400/30 text-blue-600 dark:text-blue-300">
            <Stack size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-bold text-black dark:text-white tracking-tight">
              Chunking Strategies &amp; Retrieval Representations
            </h2>
            <p className="text-xs text-black dark:text-slate-400">
              5 distinct chunking strategies forming {totalPoints.toLocaleString()} vector points in Qdrant
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-black dark:text-slate-400 font-mono">
          <Info size={14} className="text-blue-600 dark:text-blue-400" />
          <span>Automated runtime routing • No manual selection</span>
        </div>
      </div>

      <div className="space-y-6">
        <div className="flex h-3 overflow-hidden rounded-full bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10" aria-label="Indexed point distribution by representation">
          {representations.map((representation, index) => (
            <span
              key={representation.strategy}
              title={`${representation.name}: ${representation.chunk_count.toLocaleString()} points`}
              className={segmentTones[index % segmentTones.length]}
              style={{ width: `${totalPoints > 0 ? (representation.chunk_count / totalPoints) * 100 : 0}%` }}
            />
          ))}
        </div>

        {/* 5 Representation Breakdown Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {representations.map((rep, index) => (
            <div
              key={rep.strategy}
              className="flex flex-col justify-between space-y-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.03] dark:bg-white/[0.04] p-4 transition-all hover:border-blue-400/50 hover:bg-black/[0.06] dark:hover:bg-white/[0.08]"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${segmentTones[index % segmentTones.length]}`} />
                    <span className="text-sm font-bold text-black dark:text-white">{rep.name}</span>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                      rep.enabled
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                        : 'border-black/10 dark:border-white/10 bg-black/5 dark:bg-slate-500/10 text-black dark:text-slate-400'
                    }`}
                  >
                    <CheckCircle size={11} weight="fill" className="text-emerald-600 dark:text-emerald-400" /> {rep.enabled ? 'ACTIVE' : 'DISABLED'}
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-black dark:text-slate-400 min-h-[3rem]">{rep.description}</p>
              </div>
              <div className="grid grid-cols-3 gap-1.5 border-t border-black/10 dark:border-white/10 pt-3 text-center font-mono">
                <div className="rounded-lg bg-black/5 dark:bg-black/25 p-2">
                  <span className="block text-[9px] uppercase text-black dark:text-slate-500 font-sans font-semibold">Points</span>
                  <span className="text-xs font-bold text-black dark:text-white">{rep.chunk_count.toLocaleString()}</span>
                </div>
                <div className="rounded-lg bg-black/5 dark:bg-black/25 p-2">
                  <span className="block text-[9px] uppercase text-black dark:text-slate-500 font-sans font-semibold">Avg chars</span>
                  <span className="text-xs font-bold text-blue-600 dark:text-blue-300">{rep.avg_text_length}</span>
                </div>
                <div className="rounded-lg bg-black/5 dark:bg-black/25 p-2">
                  <span className="block text-[9px] uppercase text-black dark:text-slate-500 font-sans font-semibold">Artifact</span>
                  <span className="text-xs font-bold text-black dark:text-slate-300">
                    {(rep.artifact_bytes / (1024 * 1024)).toFixed(1)} MB
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </article>
  );
};
