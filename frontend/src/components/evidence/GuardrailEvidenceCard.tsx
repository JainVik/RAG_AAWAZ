import React from 'react';
import { ShieldCheck, CheckCircle, Hash, WarningCircle } from '@phosphor-icons/react';
import type { GuardrailEvidence } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface GuardrailEvidenceCardProps {
  guardrails: GuardrailEvidence;
}

export const GuardrailEvidenceCard: React.FC<GuardrailEvidenceCardProps> = ({ guardrails }) => {
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
            <ShieldCheck size={22} weight="bold" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-white tracking-tight">
                Guardrail &amp; Grounding Verification
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                {guardrails.status.replaceAll('_', ' ')}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {guardrails.observed_correct_count}/{guardrails.sample_count} observed correct · {guardrails.failed_checks.length} failed qualification checks
            </p>
          </div>
        </div>

        {/* Observed Accuracy Pill */}
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 rounded-full text-xs font-semibold">
            <CheckCircle size={14} weight="fill" className="text-emerald-400" />
            <span>{guardrails.observed_correct_count}/{guardrails.sample_count} observed correct</span>
          </span>
        </div>
      </div>

      {/* Non-Qualifying Status Alert */}
      <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-start gap-2.5">
        <WarningCircle size={18} className="shrink-0 mt-0.5" />
        <p className="leading-relaxed text-[11px]">
          <strong>Qualification notice:</strong> This report is <strong>{guardrails.status.replaceAll('_', ' ')}</strong>. {guardrails.failed_checks.length ? guardrails.failed_checks.join('; ') : 'No failed checks were reported.'}
        </p>
      </div>

      {/* Categories Passed Grid */}
      <div className="space-y-3">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
          Observed Smoke Test Policies ({guardrails.sample_count} Cases)
        </span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {guardrails.passed_categories.map((cat, idx) => (
            <div
              key={idx}
              className="p-3 bg-white/5 border border-white/8 rounded-xl flex items-center gap-2.5"
            >
              <CheckCircle size={16} className="text-emerald-400 shrink-0" weight="fill" />
              <span className="text-xs font-medium text-slate-200">{cat}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Failure Count / Summary */}
      <div className="p-3 bg-white/5 border border-white/8 rounded-xl flex items-center justify-between text-xs">
        <span className="text-slate-400">Observed Defect Rate:</span>
        <span className="font-mono font-bold text-emerald-400 flex items-center gap-1">
          <CheckCircle size={14} weight="fill" />
          <span>{guardrails.failure_count} failures across {guardrails.sample_count} observed runs</span>
        </span>
      </div>

      {/* SHA256 */}
      <div className="flex items-center gap-2 text-[10px] text-slate-400 pt-2 border-t border-white/8 font-mono">
        <Hash size={13} className="text-cyan-400 shrink-0" />
        <span className="text-slate-500">Guardrail Artifact SHA256:</span>
        <span className="truncate text-slate-300" title={guardrails.source_artifact_sha256 ?? undefined}>
          {guardrails.source_artifact_sha256 ?? 'Not available'}
        </span>
      </div>
    </GlassSurface>
  );
};
