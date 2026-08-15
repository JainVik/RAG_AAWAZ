import React from 'react';
import {
  CaretDown,
  CheckCircle,
  ShieldCheck,
  WarningCircle,
} from '@phosphor-icons/react';
import type { GuardrailEvidence } from '../../types/api';
import GlassSurface from '../ui/GlassSurface';

interface GuardrailEvidenceCardProps {
  guardrails: GuardrailEvidence;
}

export const GuardrailEvidenceCard: React.FC<GuardrailEvidenceCardProps> = ({ guardrails }) => (
  <GlassSurface
    borderRadius={20}
    brightness={35}
    opacity={0.85}
    className="space-y-6 p-6 transition-all hover:border-cyan-500/30 sm:p-8"
  >
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
      <div className="flex items-center gap-3">
        <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-2.5 text-amber-400">
          <ShieldCheck size={22} weight="bold" />
        </div>
        <div>
          <h2 className="text-base font-bold tracking-tight text-white sm:text-lg">
            Guardrail &amp; grounding verification
          </h2>
          <p className="mt-0.5 text-xs text-slate-400">
            Safety, evidence sufficiency, contradiction, deadline, and grounding behavior
          </p>
        </div>
      </div>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${
          guardrails.qualifying
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
        }`}
      >
        {guardrails.qualifying ? (
          <CheckCircle size={14} weight="fill" />
        ) : (
          <WarningCircle size={14} />
        )}
        {guardrails.qualifying ? 'Qualifying report' : 'Qualification pending'}
      </span>
    </div>

    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className="rounded-xl border border-white/8 bg-white/5 p-4">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Observed correct
        </span>
        <p className="mt-1 font-mono text-2xl font-bold text-emerald-300">
          {guardrails.observed_correct_count}/{guardrails.sample_count}
        </p>
      </div>
      <div className="rounded-xl border border-white/8 bg-white/5 p-4">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Execution failures
        </span>
        <p className="mt-1 font-mono text-2xl font-bold text-white">{guardrails.failure_count}</p>
      </div>
      <div className="rounded-xl border border-white/8 bg-white/5 p-4">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Policies exercised
        </span>
        <p className="mt-1 font-mono text-2xl font-bold text-cyan-300">
          {guardrails.passed_categories.length}
        </p>
      </div>
    </div>

    {!guardrails.qualifying && guardrails.failed_checks.length > 0 && (
      <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3.5 text-xs text-amber-300">
        <WarningCircle size={18} className="mt-0.5 shrink-0" />
        <p className="leading-relaxed">
          <strong>Still required for qualification:</strong> {guardrails.failed_checks.join('; ')}
        </p>
      </div>
    )}

    <details className="overflow-hidden rounded-xl border border-white/8 bg-black/15">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs font-bold text-slate-200">
        <span>Evaluator details · {guardrails.passed_categories.length} exercised policies</span>
        <CaretDown size={15} className="text-slate-500" />
      </summary>
      <div className="grid grid-cols-1 gap-2.5 border-t border-white/8 p-4 sm:grid-cols-2">
        {guardrails.passed_categories.map((category) => (
          <div
            key={category}
            className="flex items-center gap-2.5 rounded-xl border border-white/8 bg-white/5 p-3"
          >
            <CheckCircle size={16} className="shrink-0 text-emerald-400" weight="fill" />
            <span className="text-xs font-medium text-slate-200">{category}</span>
          </div>
        ))}
      </div>
    </details>
  </GlassSurface>
);
