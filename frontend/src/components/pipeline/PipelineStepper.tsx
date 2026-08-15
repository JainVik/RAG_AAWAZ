import React from 'react';
import {
  CircleNotch,
  CheckCircle,
  XCircle,
  HandPalm,
  ClockAfternoon,
} from '@phosphor-icons/react';
import type { BackendPipelineState, UserFacingStatusGroup } from '../../types/api';
import { PIPELINE_STATE_TO_USER_STATUS } from '../../types/api';

interface PipelineStepperProps {
  state: BackendPipelineState | null;
  timingsMs?: Record<string, number>;
  citationCount?: number;
  guardrailReason?: string | null;
}

export const PipelineStepper: React.FC<PipelineStepperProps> = ({ state, timingsMs, citationCount = 0, guardrailReason = null }) => {
  if (!state) return null;

  const userStatus: UserFacingStatusGroup = PIPELINE_STATE_TO_USER_STATUS[state] || 'Transcribing';

  const isTerminalSuccess = state === 'COMPLETED' || state === 'ANSWERED' || state === 'VERIFIED';
  const isTerminalAbstain = state === 'ABSTAINED';
  const isTerminalRepeat = state === 'NEEDS_REPEAT';
  const isTerminalUnsafe = state === 'UNSAFE';
  const isTerminalFallback = state === 'DEADLINE_FALLBACK';
  const isTerminalError = state === 'DEPENDENCY_UNAVAILABLE' || state === 'FAILED';
  const isInFlight = !isTerminalSuccess && !isTerminalAbstain && !isTerminalRepeat && !isTerminalUnsafe && !isTerminalFallback && !isTerminalError;

  // Active steps in the standard happy path pipeline
  const standardStages: { id: string; label: string; states: BackendPipelineState[] }[] = [
    { id: 'stt', label: 'Transcribing', states: ['AUDIO_RECEIVED', 'STT_PARTIAL', 'STT_FINAL'] },
    { id: 'guard', label: 'Safety check', states: ['INPUT_GUARDED'] },
    { id: 'retrieval', label: 'Retrieving evidence', states: ['SPECULATIVE_RETRIEVAL', 'RETRIEVED', 'EVIDENCE_SELECTED'] },
    { id: 'grounding', label: 'Grounding & Answer', states: ['ANSWERED', 'VERIFIED', 'COMPLETED'] },
  ];

  const completedStages = new Set<string>();
  if (state !== 'AUDIO_RECEIVED' && state !== 'STT_PARTIAL' && state !== 'STT_FINAL') {
    completedStages.add('stt');
  }
  if (['RETRIEVED', 'EVIDENCE_SELECTED', 'ANSWERED', 'VERIFIED', 'COMPLETED'].includes(state)) {
    completedStages.add('guard');
  }
  if (['EVIDENCE_SELECTED', 'ANSWERED', 'VERIFIED', 'COMPLETED'].includes(state)) {
    completedStages.add('retrieval');
  }
  if (state === 'COMPLETED') completedStages.add('grounding');

  if (state === 'ABSTAINED' || state === 'UNSAFE') completedStages.add('guard');
  if (
    state === 'ABSTAINED' &&
    ['NO_RELEVANT_EVIDENCE', 'RETRIEVAL_DISAGREEMENT'].includes(guardrailReason ?? '')
  ) {
    completedStages.add('retrieval');
  }
  if (state === 'DEADLINE_FALLBACK') {
    if (timingsMs?.input_guarded !== undefined) completedStages.add('guard');
    if (timingsMs?.retrieved !== undefined) completedStages.add('retrieval');
  }

  return (
    <div
      aria-live="polite"
      className="p-4 sm:p-5 bg-surface border border-subtle rounded-2xl shadow-xs space-y-3"
    >
      {/* Top Banner with Current Active State */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {isInFlight ? (
            <div className="p-1.5 rounded-lg bg-accent-subtle text-accent-primary">
              <CircleNotch size={18} className="animate-spin" />
            </div>
          ) : isTerminalSuccess ? (
            <div className="p-1.5 rounded-lg bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400">
              <CheckCircle size={18} weight="fill" />
            </div>
          ) : isTerminalAbstain ? (
            <div className="p-1.5 rounded-lg bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
              <HandPalm size={18} weight="fill" />
            </div>
          ) : isTerminalFallback ? (
            <div className="p-1.5 rounded-lg bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400">
              <ClockAfternoon size={18} weight="fill" />
            </div>
          ) : (
            <div className="p-1.5 rounded-lg bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-400">
              <XCircle size={18} weight="fill" />
            </div>
          )}

          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-primary">
                {userStatus}
              </span>
              <span className="font-mono text-[10px] text-muted px-1.5 py-0.2 rounded bg-surface-subtle border border-subtle">
                {state}
              </span>
            </div>
            <p className="text-[11px] text-muted">
              {isInFlight
                ? 'Processing live pipeline query across multilingual E5 and Qdrant index'
                : isTerminalSuccess
                ? 'Query completed with grounded extractive citations'
                : isTerminalAbstain
                ? 'Truthful abstention: No substantiated evidence found in corpus'
                : isTerminalFallback
                ? citationCount > 0
                  ? 'Deadline reached; returning the best available cited evidence'
                  : 'Deadline reached before a reliable cited answer was available'
                : 'Pipeline execution finished'}
            </p>
          </div>
        </div>

      </div>

      {/* Visual Pipeline Progression (When in happy path) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-subtle">
        {standardStages.map((stage) => {
          const isCurrent = isInFlight && stage.states.includes(state);
          const isPast = completedStages.has(stage.id);

          return (
            <div
              key={stage.id}
              className={`p-2 rounded-lg border text-center transition-all ${
                isCurrent
                  ? 'bg-accent-subtle/50 border-accent-primary text-accent-primary font-bold'
                  : isPast
                  ? 'bg-surface-subtle border-subtle text-secondary font-medium'
                  : 'bg-surface/50 border-transparent text-muted'
              }`}
            >
              <div className="flex items-center justify-center gap-1 text-[11px]">
                {isPast ? (
                  <CheckCircle size={12} className="text-emerald-600 dark:text-emerald-400" />
                ) : isCurrent ? (
                  <CircleNotch size={12} className="animate-spin text-accent-primary" />
                ) : (
                  <span className="w-1.5 h-1.5 rounded-full bg-border-strong" />
                )}
                <span>{stage.label}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
