import React from 'react';
import { Database, Cpu, HardDrives, ShieldCheck, Hash } from '@phosphor-icons/react';
import type { CorpusIndexInfo } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface CorpusIndexCardProps {
  corpus: CorpusIndexInfo;
}

export const CorpusIndexCard: React.FC<CorpusIndexCardProps> = ({ corpus }) => {
  const count = (value: number | null) => value === null ? 'Not available' : value.toLocaleString();
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
          <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-400/20 text-cyan-400">
            <Database size={22} weight="bold" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
              <span>Corpus &amp; Vector Index Manifest</span>
              <span className="text-xs font-normal text-slate-400 font-mono">
                ({corpus.revision})
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Verified corpus counts, embedding bindings, and vector topology
            </p>
          </div>
        </div>

        <span className={`inline-flex items-center gap-1.5 px-3 py-1 border rounded-full text-xs font-semibold ${corpus.verified ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' : 'bg-amber-500/10 text-amber-300 border-amber-500/30'}`}>
          <ShieldCheck size={14} weight="fill" className="text-emerald-400" />
          <span>{corpus.verified ? 'Manifest verified' : corpus.status.replaceAll('_', ' ')}</span>
        </span>
      </div>

      {/* Corpus Facts Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
            <HardDrives size={15} className="text-cyan-400" />
            <span>Corpus Documents</span>
          </div>
          <div className="font-mono text-2xl font-bold text-white font-mono-tabular">
            {count(corpus.document_count)}
          </div>
          <p className="text-[11px] text-slate-400">
            Unique corpus passages
          </p>
        </div>

        <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
            <Database size={15} className="text-cyan-400" />
            <span>Indexed Chunks</span>
          </div>
          <div className="font-mono text-2xl font-bold text-cyan-300 font-mono-tabular">
            {count(corpus.indexed_chunks_count)}
          </div>
          <p className="text-[11px] text-slate-400">
            Vector points across enabled representations
          </p>
        </div>

        <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
            <ShieldCheck size={15} className="text-emerald-400" />
            <span>Evaluation Fixtures</span>
          </div>
          <div className="font-mono text-2xl font-bold text-white font-mono-tabular">
            {count(corpus.evaluation_fixture_count)}
          </div>
          <p className="text-[11px] text-slate-400">
            Annotated test pairs with ground truth passage IDs
          </p>
        </div>
      </div>

      {/* Model & Vector Topology Breakdown */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
        {/* Dense Embeddings */}
        <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-2.5">
          <div className="flex items-center gap-2 text-xs font-bold text-cyan-300">
            <Cpu size={16} />
            <span>Dense Embedding Specification</span>
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-400">Model Name:</span>
              <span className="font-mono text-white font-semibold">{corpus.dense_model}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Dimension &amp; Metric:</span>
              <span className="font-mono text-cyan-300">{corpus.dense_dim}d ({corpus.dense_distance})</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Corpus Languages:</span>
              <span className="font-mono text-white">{corpus.language}</span>
            </div>
          </div>
        </div>

        {/* Vector DB & Sparse Topology */}
        <div className="p-4 bg-white/5 border border-white/8 rounded-xl space-y-2.5">
          <div className="flex items-center gap-2 text-xs font-bold text-cyan-300">
            <Database size={16} />
            <span>Vector Collection &amp; Sparse Model</span>
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-400">Qdrant Collection:</span>
              <span className="font-mono text-white font-semibold">{corpus.qdrant_collection}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Sparse Representation:</span>
              <span className="font-mono text-white">{corpus.sparse_model} (character n-grams 3-5)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Index Build ID:</span>
              <span className="font-mono text-cyan-300">{corpus.index_build_id}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Manifest SHA256 */}
      <div className="flex items-center gap-2 text-[10px] text-slate-400 pt-2 border-t border-white/8 font-mono">
        <Hash size={13} className="text-cyan-400 shrink-0" />
        <span className="text-slate-500">Corpus Manifest SHA256:</span>
        <span className="truncate text-slate-300" title={corpus.source_artifact_sha256 ?? undefined}>
          {corpus.source_artifact_sha256 ?? 'Not available'}
        </span>
      </div>
    </GlassSurface>
  );
};
