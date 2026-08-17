import React, { useState } from 'react';
import {
  Check,
  Copy,
  HandPalm,
  Quotes,
  Sparkle,
  SpinnerGap,
  WarningOctagon,
} from '@phosphor-icons/react';
import type { QueryResponse, SynthesisResponse } from '../../types/api';
import { getLanguageDisplayLabel, PIPELINE_STATE_TO_USER_STATUS } from '../../types/api';
import { CitationDrawer } from '../citations/CitationDrawer';
import { QueryLatencySummary } from '../pipeline/QueryLatencySummary';
import {
  getSynthesisLatencyMs,
  getResponseLatencyMs,
  formatResponseLatency,
} from '../../utils/responseTiming';

interface AnswerCardsProps {
  result: QueryResponse;
  synthesisLoading: boolean;
  synthesisResult: SynthesisResponse | null;
  synthesisError: string | null;
  onDismiss: () => void;
}

type DrawerSource = 'primary' | 'synthesis' | null;
type CopySource = 'primary' | 'synthesis' | null;

interface UninvokedSynthesisState {
  status: 'out of context' | 'not generated';
  title: 'Out of context' | 'Not generated';
  message: string;
}

const SYNTHESIS_FAILURE_MESSAGES: Record<Exclude<SynthesisResponse['status'], 'completed'>, string> = {
  abstained: 'The model did not find enough grounded evidence to produce a reliable synthesis.',
  timed_out: 'The synthesis exceeded its time budget. The evidence answer remains available.',
  unavailable: 'Groq synthesis is temporarily unavailable. The evidence answer remains available.',
  grounding_failed: 'A generated draft was withheld because its claims were not fully supported.',
};

function modelDisplayName(model: string): string {
  const shortName = model.split('/').at(-1) || model;
  return shortName.replaceAll('-', ' ').toUpperCase();
}

function synthesisFailureTitle(result: SynthesisResponse | null): string {
  if (result?.status === 'abstained') return 'Synthesis abstained';
  if (result?.status === 'timed_out') return 'Synthesis timed out';
  if (result?.status === 'grounding_failed') return 'Ungrounded draft withheld';
  return 'Synthesis unavailable';
}

function getUninvokedSynthesisState(result: QueryResponse): UninvokedSynthesisState {
  const { decision, reason } = result.guardrail;

  if (
    result.state === 'UNSAFE' ||
    decision === 'BLOCK' ||
    reason === 'UNSAFE_REQUEST' ||
    reason === 'PROMPT_INJECTION'
  ) {
    return {
      status: 'not generated',
      title: 'Not generated',
      message: 'Groq was not invoked because the request was blocked by safety checks.',
    };
  }

  if (result.state === 'NEEDS_REPEAT' || decision === 'NEEDS_REPEAT') {
    return {
      status: 'not generated',
      title: 'Not generated',
      message:
        'Groq was not invoked because the question needs to be repeated before a verified evidence answer can be prepared.',
    };
  }

  if (result.state === 'DEPENDENCY_UNAVAILABLE' || reason === 'DEPENDENCY_UNAVAILABLE') {
    return {
      status: 'not generated',
      title: 'Not generated',
      message: 'Groq was not invoked because a required service was unavailable.',
    };
  }

  if (result.state === 'DEADLINE_FALLBACK' || reason === 'DEADLINE_EXCEEDED') {
    return {
      status: 'not generated',
      title: 'Not generated',
      message:
        'Groq was not invoked because the primary request reached its deadline before a verified evidence answer was available.',
    };
  }

  if (result.state === 'FAILED') {
    return {
      status: 'not generated',
      title: 'Not generated',
      message:
        'Groq was not invoked because the primary request failed before a verified evidence answer was available.',
    };
  }

  return {
    status: 'out of context',
    title: 'Out of context',
    message: 'Groq was not invoked because no verified corpus evidence was available.',
  };
}

export function sanitizeQueryResponseForDisplay(result: QueryResponse): Record<string, unknown> {
  if (!result.synthesis) return result as unknown as Record<string, unknown>;
  return {
    ...result,
    synthesis: {
      available: true,
      provider: result.synthesis.provider,
      model: result.synthesis.model,
      expires_in_ms: result.synthesis.expires_in_ms,
    },
  };
}

export const AnswerCards: React.FC<AnswerCardsProps> = ({
  result,
  synthesisLoading,
  synthesisResult,
  synthesisError,
}) => {
  const [drawerSource, setDrawerSource] = useState<DrawerSource>(null);
  const [copied, setCopied] = useState<CopySource>(null);
  const synthesisLatencyMs = getSynthesisLatencyMs(synthesisResult?.timings_ms);
  const responseLatencyMs = getResponseLatencyMs(result.timings_ms);
  const primaryOutcome =
    result.guardrail.decision === 'ALLOW' && result.answer && result.citations.length > 0
      ? 'Grounded'
      : PIPELINE_STATE_TO_USER_STATUS[result.state];
  const uninvokedSynthesis =
    !result.answer &&
    !result.synthesis &&
    !synthesisLoading &&
    !synthesisResult &&
    !synthesisError
      ? getUninvokedSynthesisState(result)
      : null;
  const hasSynthesisCard = Boolean(
    result.synthesis || synthesisLoading || synthesisResult || synthesisError || uninvokedSynthesis
  );
  const synthesisModel = synthesisResult?.model ?? result.synthesis?.model ?? '';
  const synthesisProvider = synthesisResult?.provider ?? result.synthesis?.provider ?? 'groq';

  const copyAnswer = async (source: Exclude<CopySource, null>, answer: string | null) => {
    if (!answer) return;
    await navigator.clipboard.writeText(answer);
    setCopied(source);
    window.setTimeout(() => setCopied(null), 1500);
  };

  const primaryCard = (
    <article className="refractive-glass-card refractive-glass-card-primary flex h-full min-w-0 flex-col space-y-4 p-6 text-left">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-black/10 dark:border-white/10 pb-3 text-xs text-black dark:text-slate-400">
        <div>
          <span className="flex items-center gap-1.5 font-semibold text-blue-600 dark:text-blue-400">
            <Sparkle size={14} weight="fill" />Evidence answer
          </span>
          <span className="mt-1 block text-[10px] text-slate-600 dark:text-slate-400">Exact answer assembled from retrieved passages</span>
        </div>
      </div>

      <div className="flex-1">
        {result.answer ? (
          <p className="select-text whitespace-pre-wrap break-words text-base leading-relaxed text-black dark:text-white font-normal">
            {result.answer}
          </p>
        ) : result.guardrail.decision === 'ABSTAIN' || result.state === 'ABSTAINED' ? (
          <div className="glass-inner-box flex gap-2.5 text-xs text-black dark:text-slate-200">
            <HandPalm size={18} className="shrink-0 text-slate-500 dark:text-slate-400" />
            <span className="leading-relaxed text-black dark:text-slate-300">
              {result.guardrail.user_message ?? 'The corpus does not contain enough verified evidence.'}
            </span>
          </div>
        ) : (
          <div className="glass-inner-box flex gap-2.5 text-xs text-rose-800 dark:text-rose-300">
            <WarningOctagon size={18} className="shrink-0 text-rose-500" />
            <span className="leading-relaxed">
              {result.guardrail.user_message ?? `Request ended in ${result.state}.`}
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-black/10 dark:border-white/10 pt-3">
        <button
          type="button"
          disabled={!result.citations.length}
          onClick={() => setDrawerSource('primary')}
          className="glass-btn inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold text-blue-600 dark:text-blue-300 disabled:opacity-40"
        >
          <Quotes size={15} weight="fill" />
          {result.citations.length} citation{result.citations.length === 1 ? '' : 's'}
        </button>
        {result.answer && (
          <button
            type="button"
            onClick={() => void copyAnswer('primary', result.answer)}
            className="inline-flex items-center gap-1 text-xs text-black hover:text-black dark:text-slate-400 dark:hover:text-white transition-colors cursor-pointer font-medium"
          >
            {copied === 'primary' ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
            {copied === 'primary' ? 'Copied' : 'Copy answer'}
          </button>
        )}
      </div>
    </article>
  );

  const synthesisCard = hasSynthesisCard ? (
    <article
      aria-busy={synthesisLoading}
      className="refractive-glass-card refractive-glass-card-synthesis flex h-full min-w-0 flex-col space-y-4 p-6 text-left"
    >
      <div className="border-b border-black/10 dark:border-white/10 pb-3 text-xs text-black dark:text-slate-400">
        <span className="flex items-center gap-1.5 font-semibold text-violet-600 dark:text-violet-300">
          <Sparkle size={14} weight="fill" />Groq grounded synthesis
        </span>
        <span className="mt-1 block text-[10px] text-slate-600 dark:text-slate-400">Natural-language answer constrained to the retrieved evidence</span>
      </div>

      <div className="flex flex-1 flex-col justify-center" aria-live="polite">
        {synthesisLoading ? (
          <div className="glass-inner-box flex items-center gap-3 text-sm text-violet-900 dark:text-violet-200">
            <SpinnerGap size={20} className="shrink-0 animate-spin text-violet-600 dark:text-violet-300" />
            <div>
              <p className="font-semibold text-black dark:text-white">Preparing the grounded synthesis…</p>
              <p className="mt-1 text-xs text-black dark:text-slate-400">Your evidence answer is already ready.</p>
            </div>
          </div>
        ) : synthesisResult?.status === 'completed' && synthesisResult.answer ? (
          <div>
            <p className="select-text whitespace-pre-wrap break-words text-base leading-relaxed text-black dark:text-white font-normal">
              {synthesisResult.answer}
            </p>
          </div>
        ) : uninvokedSynthesis ? (
          <div className="glass-inner-box flex gap-3 text-sm text-black dark:text-slate-200">
            <HandPalm size={20} className="shrink-0 text-slate-500 dark:text-slate-400" />
            <div>
              <p className="font-semibold text-black dark:text-white">{uninvokedSynthesis.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-black dark:text-slate-300">
                {uninvokedSynthesis.message}
              </p>
            </div>
          </div>
        ) : (
          <div className="glass-inner-box flex gap-3 text-sm text-black dark:text-slate-200">
            <WarningOctagon size={20} className="shrink-0 text-slate-500 dark:text-slate-400" />
            <div>
              <p className="font-semibold text-black dark:text-white">{synthesisFailureTitle(synthesisResult)}</p>
              <p className="mt-1 text-xs leading-relaxed text-black dark:text-slate-300">
                {synthesisError ??
                  (synthesisResult && synthesisResult.status !== 'completed'
                    ? synthesisResult.guardrail.user_message ?? SYNTHESIS_FAILURE_MESSAGES[synthesisResult.status]
                    : 'The grounded synthesis could not be loaded. The evidence answer remains available.')}
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-black/10 dark:border-white/10 pt-3">
        <button
          type="button"
          disabled={!synthesisResult?.citations.length}
          onClick={() => setDrawerSource('synthesis')}
          className="glass-btn inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold text-violet-600 dark:text-violet-200 disabled:opacity-40"
        >
          <Quotes size={15} weight="fill" />
          {synthesisResult?.citations.length ?? 0} citation{(synthesisResult?.citations.length ?? 0) === 1 ? '' : 's'}
        </button>
        {synthesisResult?.answer && (
          <button
            type="button"
            onClick={() => void copyAnswer('synthesis', synthesisResult.answer)}
            className="inline-flex items-center gap-1 text-xs text-black hover:text-black dark:text-slate-400 dark:hover:text-white transition-colors cursor-pointer font-medium"
          >
            {copied === 'synthesis' ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
            {copied === 'synthesis' ? 'Copied' : 'Copy answer'}
          </button>
        )}
      </div>
    </article>
  ) : null;

  const drawerIsSynthesis = drawerSource === 'synthesis' && synthesisResult !== null;
  const drawerCitations = drawerIsSynthesis ? synthesisResult.citations : result.citations;
  const drawerPayload = drawerIsSynthesis
    ? synthesisResult
    : sanitizeQueryResponseForDisplay(result);

  return (
    <>
      <section
        aria-label="Query answers"
        className={`w-full ${hasSynthesisCard ? 'max-w-5xl' : 'max-w-xl'}`}
      >
        <div className={`grid items-stretch gap-4 ${hasSynthesisCard ? 'lg:grid-cols-2' : ''}`}>
          {primaryCard}
          {synthesisCard}
        </div>

        {/* Outcome & Latency Summary Pills aligned to card columns */}
        <div className={`mt-3.5 grid gap-4 ${hasSynthesisCard ? 'lg:grid-cols-2' : ''}`}>
          {/* Left Column Pill (Evidence Answer) */}
          <div className="flex justify-center">
            <div aria-label="Query outcome summary" className="refractive-glass-pill flex items-center gap-x-2 px-3.5 py-1.5 font-mono text-[10px] text-black dark:text-slate-300">
              <span className="inline-flex items-center gap-1 font-bold text-blue-600 dark:text-blue-300">
                <Sparkle size={12} weight="fill" /> Evidence Answer
              </span>
              <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
              <span className="text-blue-600 dark:text-blue-300">{getLanguageDisplayLabel(result.language)}</span>
              <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
              <span className={primaryOutcome === 'Grounded' ? 'text-emerald-600 dark:text-emerald-300 font-semibold' : 'text-amber-600 dark:text-amber-300'}>{primaryOutcome}</span>
              <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
              <span>{result.citations.length} citation{result.citations.length === 1 ? '' : 's'}</span>
              {responseLatencyMs !== null && (
                <>
                  <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
                  <span className="font-bold text-blue-600 dark:text-blue-300">{formatResponseLatency(responseLatencyMs)}</span>
                </>
              )}
            </div>
          </div>

          {/* Right Column Pill (Groq Grounded Synthesis) */}
          {hasSynthesisCard && (
            <div className="flex justify-center">
              <div className="refractive-glass-pill flex items-center gap-x-2 px-3.5 py-1.5 font-mono text-[10px] text-black dark:text-slate-300">
                <span className="inline-flex items-center gap-1 font-bold text-violet-600 dark:text-violet-300">
                  <Sparkle size={12} weight="fill" /> Groq Synthesis
                </span>
                {synthesisModel && (
                  <>
                    <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
                    <span className="text-violet-600 dark:text-violet-200 font-medium">{modelDisplayName(synthesisModel)}</span>
                  </>
                )}
                <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
                <span className={synthesisResult?.status === 'completed' ? 'text-emerald-600 dark:text-emerald-300 font-semibold' : 'text-violet-600 dark:text-violet-300'}>
                  {synthesisResult?.status === 'completed' ? 'Grounded' : synthesisLoading ? 'Generating…' : (synthesisResult?.status ?? 'Pending')}
                </span>
                {synthesisResult?.citations && (
                  <>
                    <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
                    <span>{synthesisResult.citations.length} citation{synthesisResult.citations.length === 1 ? '' : 's'}</span>
                  </>
                )}
                {synthesisLatencyMs !== null && (
                  <>
                    <span className="text-slate-400 dark:text-slate-600" aria-hidden="true">·</span>
                    <span className="font-bold text-violet-600 dark:text-violet-300">Generated in {formatResponseLatency(synthesisLatencyMs)}</span>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        <QueryLatencySummary timingsMs={result.timings_ms} responseLatencyMs={responseLatencyMs} />
      </section>
      <CitationDrawer
        isOpen={drawerSource !== null}
        onClose={() => setDrawerSource(null)}
        citations={drawerCitations}
        title={drawerIsSynthesis ? 'Synthesis citations' : 'Grounded citations'}
        subtitle={`${drawerCitations.length} exact evidence span${drawerCitations.length === 1 ? '' : 's'} from MSMARCO-XI`}
        badge={drawerIsSynthesis ? `${synthesisProvider} · ${synthesisModel}` : result.answer_mode}
        evidenceAgreement={drawerIsSynthesis ? null : result.evidence_agreement}
        rawPayload={drawerPayload}
      />
    </>
  );
};
