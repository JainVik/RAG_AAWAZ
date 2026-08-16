import React, { useState } from 'react';
import {
  Check,
  Copy,
  HandPalm,
  Quotes,
  Sparkle,
  SpinnerGap,
  WarningOctagon,
  X,
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
  onDismiss,
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
    <article className="flex h-full min-w-0 flex-col space-y-4 rounded-2xl border border-cyan-500/30 bg-[#0e1529]/90 p-6 text-left shadow-2xl">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/10 pb-3 text-xs text-slate-400">
        <div>
          <span className="flex items-center gap-1.5 font-semibold text-cyan-400">
            <Sparkle size={14} weight="fill" />Evidence answer
          </span>
          <span className="mt-1 block text-[10px] text-slate-500">Exact answer assembled from retrieved passages</span>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            aria-label="Dismiss answers"
            title="Dismiss answers"
            onClick={onDismiss}
            className="rounded-md p-1 text-slate-400 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <p className="select-text break-words text-xs italic text-slate-300">“{result.transcript}”</p>
      <div className="flex-1">
        {result.answer ? (
          <p className="select-text whitespace-pre-wrap break-words text-base leading-relaxed text-white">
            {result.answer}
          </p>
        ) : result.guardrail.decision === 'ABSTAIN' || result.state === 'ABSTAINED' ? (
          <div className="flex gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-300">
            <HandPalm size={18} className="shrink-0" />
            {result.guardrail.user_message ?? 'The corpus does not contain enough verified evidence.'}
          </div>
        ) : (
          <div className="flex gap-2 rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-xs text-rose-300">
            <WarningOctagon size={18} className="shrink-0" />
            {result.guardrail.user_message ?? `Request ended in ${result.state}.`}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3">
        <button
          type="button"
          disabled={!result.citations.length}
          onClick={() => setDrawerSource('primary')}
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 disabled:opacity-40"
        >
          <Quotes size={15} weight="fill" />
          {result.citations.length} citation{result.citations.length === 1 ? '' : 's'}
        </button>
        {result.answer && (
          <button
            type="button"
            onClick={() => void copyAnswer('primary', result.answer)}
            className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white"
          >
            {copied === 'primary' ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
            {copied === 'primary' ? 'Copied' : 'Copy answer'}
          </button>
        )}
      </div>
    </article>
  );

  const synthesisCard = hasSynthesisCard ? (
    <article
      aria-busy={synthesisLoading}
      className="flex h-full min-w-0 flex-col space-y-4 rounded-2xl border border-violet-400/30 bg-[#11152b]/95 p-6 text-left shadow-2xl"
    >
      <div className="border-b border-white/10 pb-3 text-xs text-slate-400">
        <span className="flex items-center gap-1.5 font-semibold text-violet-300">
          <Sparkle size={14} weight="fill" />Groq grounded synthesis
        </span>
        <span className="mt-1 block text-[10px] text-slate-500">Natural-language answer constrained to the retrieved evidence</span>
      </div>

      <div className="flex flex-1 flex-col justify-center" aria-live="polite">
        {synthesisLoading ? (
          <div className="flex items-center gap-3 rounded-xl border border-violet-400/15 bg-violet-500/5 p-4 text-sm text-violet-200">
            <SpinnerGap size={20} className="shrink-0 animate-spin" />
            <div>
              <p className="font-semibold">Preparing the grounded synthesis…</p>
              <p className="mt-1 text-xs text-slate-400">Your evidence answer is already ready.</p>
            </div>
          </div>
        ) : synthesisResult?.status === 'completed' && synthesisResult.answer ? (
          <div>
            <p className="select-text whitespace-pre-wrap break-words text-base leading-relaxed text-white">
              {synthesisResult.answer}
            </p>
            <p className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-violet-300/75">
              {synthesisResult.claims.length} grounded claim{synthesisResult.claims.length === 1 ? '' : 's'} verified
            </p>
          </div>
        ) : uninvokedSynthesis ? (
          <div className="flex gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-200">
            <HandPalm size={20} className="shrink-0" />
            <div>
              <p className="font-semibold">{uninvokedSynthesis.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-amber-100/75">
                {uninvokedSynthesis.message}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-200">
            <WarningOctagon size={20} className="shrink-0" />
            <div>
              <p className="font-semibold">{synthesisFailureTitle(synthesisResult)}</p>
              <p className="mt-1 text-xs leading-relaxed text-amber-100/75">
                {synthesisError ??
                  (synthesisResult && synthesisResult.status !== 'completed'
                    ? synthesisResult.guardrail.user_message ?? SYNTHESIS_FAILURE_MESSAGES[synthesisResult.status]
                    : 'The grounded synthesis could not be loaded. The evidence answer remains available.')}
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3">
        <button
          type="button"
          disabled={!synthesisResult?.citations.length}
          onClick={() => setDrawerSource('synthesis')}
          className="inline-flex items-center gap-2 rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-200 disabled:opacity-40"
        >
          <Quotes size={15} weight="fill" />
          {synthesisResult?.citations.length ?? 0} citation{(synthesisResult?.citations.length ?? 0) === 1 ? '' : 's'}
        </button>
        {synthesisResult?.answer && (
          <button
            type="button"
            onClick={() => void copyAnswer('synthesis', synthesisResult.answer)}
            className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white"
          >
            {copied === 'synthesis' ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
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
            <div className="flex items-center gap-x-2 rounded-full border border-cyan-500/30 bg-[#0a1324]/90 px-3.5 py-1.5 font-mono text-[10px] text-slate-300 shadow-sm backdrop-blur-sm">
              <span className="inline-flex items-center gap-1 font-bold text-cyan-300">
                <Sparkle size={12} weight="fill" /> Evidence Answer
              </span>
              <span className="text-slate-600" aria-hidden="true">·</span>
              <span className="text-cyan-300">{getLanguageDisplayLabel(result.language)}</span>
              <span className="text-slate-600" aria-hidden="true">·</span>
              <span className={primaryOutcome === 'Grounded' ? 'text-emerald-300 font-semibold' : 'text-amber-300'}>{primaryOutcome}</span>
              <span className="text-slate-600" aria-hidden="true">·</span>
              <span>{result.citations.length} citation{result.citations.length === 1 ? '' : 's'}</span>
              {responseLatencyMs !== null && (
                <>
                  <span className="text-slate-600" aria-hidden="true">·</span>
                  <span className="font-bold text-cyan-300">{formatResponseLatency(responseLatencyMs)}</span>
                </>
              )}
            </div>
          </div>

          {/* Right Column Pill (Groq Grounded Synthesis) */}
          {hasSynthesisCard && (
            <div className="flex justify-center">
              <div className="flex items-center gap-x-2 rounded-full border border-violet-500/30 bg-[#140e29]/90 px-3.5 py-1.5 font-mono text-[10px] text-slate-300 shadow-sm backdrop-blur-sm">
                <span className="inline-flex items-center gap-1 font-bold text-violet-300">
                  <Sparkle size={12} weight="fill" /> Groq Synthesis
                </span>
                {synthesisModel && (
                  <>
                    <span className="text-slate-600" aria-hidden="true">·</span>
                    <span className="text-violet-200 font-medium">{modelDisplayName(synthesisModel)}</span>
                  </>
                )}
                <span className="text-slate-600" aria-hidden="true">·</span>
                <span className={synthesisResult?.status === 'completed' ? 'text-emerald-300 font-semibold' : 'text-violet-300'}>
                  {synthesisResult?.status === 'completed' ? 'Grounded' : synthesisLoading ? 'Generating…' : (synthesisResult?.status ?? 'Pending')}
                </span>
                {synthesisResult?.status === 'completed' && (
                  <>
                    <span className="text-slate-600" aria-hidden="true">·</span>
                    <span>{synthesisResult.citations.length} citation{synthesisResult.citations.length === 1 ? '' : 's'}</span>
                  </>
                )}
                {synthesisLatencyMs !== null && (
                  <>
                    <span className="text-slate-600" aria-hidden="true">·</span>
                    <span className="font-bold text-violet-300">{formatResponseLatency(synthesisLatencyMs)}</span>
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
