import React from 'react';
import {
  FileText,
  CheckCircle,
  ListNumbers,
  ChartPieSlice,
  ShieldWarning,
} from '@phosphor-icons/react';
import type { DatasetAuditInfo } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface DatasetAuditCardProps {
  audit: DatasetAuditInfo;
}

export const DatasetAuditCard: React.FC<DatasetAuditCardProps> = ({ audit }) => {
  const defectCount = audit.malformed_row_count + audit.duplicate_query_count;
  return (
    <GlassSurface
      borderRadius={20}
      brightness={35}
      opacity={0.85}
      className="p-6 transition-all hover:border-blue-500/30"
    >
      <div className="space-y-6">
        {/* Header & Qualification Status */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-400/20 text-blue-400">
              <FileText size={22} weight="bold" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white tracking-tight">
                  Dataset Audit (Smoke Sample)
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                  Artifact sample audit
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Audited validation slice • Not a full-dataset certification
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-slate-400">Scope:</span>
            <span className="px-2.5 py-1 rounded-lg text-xs font-mono font-bold bg-white/5 border border-white/10 text-blue-300">
              {audit.audited_row_count} Rows Audited
            </span>
          </div>
        </div>

        {/* Audit Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {/* Schema Match */}
          <div className="p-3.5 bg-white/5 border border-white/8 rounded-xl space-y-1">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Schema Match
            </span>
            <div className="flex items-center gap-1.5 text-emerald-400 font-bold text-sm">
              <CheckCircle size={16} weight="fill" />
              <span>{audit.schema_match === null ? 'Not measured' : audit.schema_match ? '100% Matched' : 'Mismatch'}</span>
            </div>
            <span className="text-[10px] text-slate-500 block">Strict type match</span>
          </div>

          {/* Malformed & Duplicates */}
          <div className="p-3.5 bg-white/5 border border-white/8 rounded-xl space-y-1">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Malformed / Dupes
            </span>
            <span className="text-white font-mono font-bold text-sm block">
              {audit.malformed_row_count} / {audit.duplicate_query_count}
            </span>
            <span className={`text-[10px] block font-medium ${defectCount === 0 ? 'text-emerald-400' : 'text-amber-300'}`}>
              {defectCount === 0 ? '0 defects detected' : `${defectCount} observed defect${defectCount === 1 ? '' : 's'}`}
            </span>
          </div>

          {/* Candidate Passages */}
          <div className="p-3.5 bg-white/5 border border-white/8 rounded-xl space-y-1">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Candidate Passages
            </span>
            <span className="text-white font-mono font-bold text-sm block">
              {audit.candidate_passage_count}
            </span>
            <span className="text-[10px] text-slate-500 block">Across {audit.audited_row_count} audited queries</span>
          </div>

          {/* Selected Passage Ratio */}
          <div className="p-3.5 bg-white/5 border border-white/8 rounded-xl space-y-1">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Passage Hit Ratio
            </span>
            <span className="text-blue-400 font-mono font-bold text-sm block">
              {audit.selected_passage_ratio === null ? 'Not measured' : `${(audit.selected_passage_ratio * 100).toFixed(1)}%`}
            </span>
            <span className="text-[10px] text-slate-500 block">Selected candidate ratio</span>
          </div>
        </div>

        {/* Query Type Distribution & Dataset Metadata */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Query Type Distribution */}
          <div className="p-3.5 bg-white/5 border border-white/8 rounded-xl space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300">
              <ChartPieSlice size={15} className="text-blue-400" />
              <span>Query Type Distribution</span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center pt-1">
              {Object.entries(audit.query_type_distribution || {}).map(([type, count]) => (
                <div key={type} className="p-2 bg-white/5 rounded-lg border border-white/5">
                  <span className="text-xs font-bold text-white font-mono">{count}</span>
                  <span className="text-[10px] text-slate-400 block mt-0.5">{type}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Dataset Pinned Details */}
          <div className="p-3.5 bg-white/5 border border-white/8 rounded-xl space-y-1.5 text-xs">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300 mb-1">
              <ListNumbers size={15} className="text-blue-400" />
              <span>Provenance &amp; Split</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">Dataset ID:</span>
              <span className="font-mono text-slate-200">{audit.dataset_id}</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">Source Split:</span>
              <span className="font-mono text-slate-200">{audit.source_split} ({audit.target_language})</span>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">Revision:</span>
              <span className="font-mono text-slate-200">{audit.revision}</span>
            </div>
          </div>
        </div>

        {/* Certification Boundary Alert */}
        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-start gap-2.5">
          <ShieldWarning size={18} className="shrink-0 mt-0.5" />
          <p className="leading-relaxed text-[11px]">
            <strong>Audit boundary:</strong> This validates format integrity and passage selection on {audit.audited_row_count} retained rows. It is not a full-dataset certification.
          </p>
        </div>

      </div>
    </GlassSurface>
  );
};
