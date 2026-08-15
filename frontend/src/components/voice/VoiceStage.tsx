import React, { useState } from 'react';
import { Check, Copy, HandPalm, Lightning, Quotes, Sparkle, WarningOctagon, X } from '@phosphor-icons/react';
import type { LanguageHint, PipelineState, QueryResponse, VoiceErrorState, VoiceState } from '../../types/api';
import { getLanguageDisplayLabel, PIPELINE_STATE_TO_USER_STATUS } from '../../types/api';
import { VoiceOrb } from './VoiceOrb';
import { VoicePillControls } from './VoicePillControls';
import { CitationDrawer } from '../citations/CitationDrawer';
import { PipelineStepper } from '../pipeline/PipelineStepper';
import { formatResponseLatency, getResponseLatencyMs } from '../../utils/responseTiming';

interface VoiceStageProps {
  state: VoiceState;
  pipelineState: PipelineState | null;
  error: VoiceErrorState | null;
  recordingDuration: number;
  audioLevel: number;
  selectedLanguage: LanguageHint;
  detectedLanguage: string | null;
  partialTranscript: string;
  result: QueryResponse | null;
  canSubmit: boolean;
  onLanguageChange: (language: LanguageHint) => void;
  onStartRecording: () => void;
  onStopAndAsk: () => void;
  onCancelRecording: () => void;
  onReset: () => void;
  onToggleTextMode: () => void;
  onSelectSamplePrompt: (prompt: string) => void;
  onOpenDiagnostics?: () => void;
}

const SAMPLE_PROMPTS = [
  { label: 'English', text: 'What is gold\'s hardness on the Mohs scale?' },
  { label: 'Hindi', text: 'डायसेफैलिक सिंड्रोम को परिभाषित करें।' },
  { label: 'English', text: 'What are the symptoms of a strained leg muscle?' },
];

export const VoiceStage: React.FC<VoiceStageProps> = (props) => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const isRecording = props.state === 'recording';
  const isProcessing = props.state === 'processing';
  const isRequesting = props.state === 'requesting_permission';
  const effectiveState = props.result?.state ?? props.pipelineState;
  const responseLatencyMs = getResponseLatencyMs(props.result?.timings_ms);

  const copyAnswer = async () => {
    if (!props.result?.answer) return;
    await navigator.clipboard.writeText(props.result.answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="relative flex min-h-[calc(100dvh-100px)] select-none flex-col items-center justify-between px-4 py-6">
      <div className="flex h-8 items-center justify-center">
        {props.detectedLanguage && props.detectedLanguage !== 'unknown' && <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-cyan-300">Detected: {getLanguageDisplayLabel(props.detectedLanguage)}</div>}
      </div>

      <div className={`my-auto flex w-full max-w-2xl flex-col items-center justify-center py-4 text-center ${isRecording ? '-translate-y-4 space-y-4' : 'space-y-6'}`}>
        <VoiceOrb state={props.state} audioLevel={props.audioLevel} disabled={!props.canSubmit || isProcessing || isRequesting || props.state === 'terminal'} onClick={isRecording ? props.onStopAndAsk : props.onStartRecording} />

        {effectiveState && <div className="w-full"><PipelineStepper state={effectiveState} timingsMs={props.result?.timings_ms} citationCount={props.result?.citations.length ?? 0} guardrailReason={props.result?.guardrail.reason ?? null} /></div>}

        <div className="flex min-h-[100px] flex-col items-center justify-center space-y-3 px-4 pb-3">
          {isRecording ? <><h2 className="text-3xl font-bold text-white">Listening…</h2><p className="max-w-xl text-base leading-relaxed text-cyan-300">{props.partialTranscript || 'Speak your complete question.'}</p><span className="text-[10px] text-slate-500">Live draft — auto-stops after 1.5 seconds of silence</span></> :
            isRequesting ? <><h2 className="text-2xl font-bold text-white">Requesting microphone…</h2><p className="text-xs text-slate-400">Allow microphone access in the browser prompt.</p></> :
            isProcessing ? <><h2 className="text-2xl font-bold text-white">{effectiveState ? PIPELINE_STATE_TO_USER_STATUS[effectiveState] : 'Processing…'}</h2><p className="text-xs text-slate-400">Searching the verified MSMARCO-XI evidence index.</p></> :
            props.result ? (
              <div className="w-full max-w-xl space-y-4 rounded-2xl border border-cyan-500/30 bg-[#0e1529]/90 p-6 text-left shadow-2xl">
                <div className="flex items-center justify-between border-b border-white/10 pb-3 text-xs text-slate-400">
                  <span className="flex items-center gap-1.5 font-semibold text-cyan-400"><Sparkle size={14} weight="fill" />{props.result.state}</span>
                  <div className="flex items-center gap-3">
                    {responseLatencyMs !== null && (
                      <span
                        title="Backend-measured processing time after final input; network and browser rendering excluded"
                        className="inline-flex items-center gap-1 rounded-full border border-emerald-400/25 bg-emerald-500/10 px-2 py-1 font-mono text-[11px] font-semibold text-emerald-300"
                      >
                        <Lightning size={13} weight="fill" />
                        Responded in {formatResponseLatency(responseLatencyMs)}
                      </span>
                    )}
                    <span className="font-mono">{props.result.answer_mode}</span>
                    <button
                      type="button"
                      aria-label="Dismiss answer"
                      title="Dismiss answer"
                      onClick={() => {
                        setDrawerOpen(false);
                        props.onReset();
                      }}
                      className="rounded-md p-1 text-slate-400 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                    >
                      <X size={16} />
                    </button>
                  </div>
                </div>
                <p className="text-xs italic text-slate-300">“{props.result.transcript}”</p>
                {props.result.answer ? <p className="text-base leading-relaxed text-white">{props.result.answer}</p> : props.result.guardrail.decision === 'ABSTAIN' || props.result.state === 'ABSTAINED' ? <div className="flex gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-300"><HandPalm size={18} />{props.result.guardrail.user_message ?? 'The corpus does not contain enough verified evidence.'}</div> : <div className="flex gap-2 rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-xs text-rose-300"><WarningOctagon size={18} />{props.result.guardrail.user_message ?? `Request ended in ${props.result.state}.`}</div>}
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3">
                  <button type="button" disabled={!props.result.citations.length} onClick={() => setDrawerOpen(true)} className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 disabled:opacity-40"><Quotes size={15} weight="fill" />{props.result.citations.length} citation{props.result.citations.length === 1 ? '' : 's'}</button>
                  {props.result.answer && <button type="button" onClick={() => void copyAnswer()} className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white">{copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy answer'}</button>}
                </div>
              </div>
            ) : <><h2 className="text-3xl font-bold text-white">Ask with voice or text</h2><p className="text-sm text-slate-400">Validated corpus paths: English, Hindi, and Hinglish. Other provider languages remain experimental.</p><div className="flex flex-wrap justify-center gap-2 pt-2">{SAMPLE_PROMPTS.map((prompt) => <button key={prompt.text} type="button" disabled={!props.canSubmit} onClick={() => props.onSelectSamplePrompt(prompt.text)} className="max-w-[280px] truncate rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs text-slate-300 disabled:opacity-40"><span className="mr-1.5 font-mono text-[10px] text-cyan-400">[{prompt.label}]</span>{prompt.text}</button>)}</div></>}

          {props.error && !props.result && <div className="max-w-md rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">{props.error.message}</div>}
          {!props.canSubmit && !props.result && <button type="button" onClick={props.onOpenDiagnostics} className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">Backend not ready — view checks</button>}
        </div>
      </div>

      <VoicePillControls {...props} state={props.state} onSelectSamplePrompt={props.onSelectSamplePrompt} />
      <CitationDrawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} result={props.result} />
    </div>
  );
};
