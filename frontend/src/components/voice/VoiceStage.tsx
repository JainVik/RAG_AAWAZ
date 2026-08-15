import React from 'react';
import type { LanguageHint, PipelineState, QueryResponse, SynthesisResponse, VoiceErrorState, VoiceState } from '../../types/api';
import { getLanguageDisplayLabel, PIPELINE_STATE_TO_USER_STATUS } from '../../types/api';
import { VoiceOrb } from './VoiceOrb';
import { VoicePillControls } from './VoicePillControls';
import { PipelineStepper } from '../pipeline/PipelineStepper';
import { AnswerCards } from './AnswerCards';

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
  synthesisLoading: boolean;
  synthesisResult: SynthesisResponse | null;
  synthesisError: string | null;
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
  const isRecording = props.state === 'recording';
  const isProcessing = props.state === 'processing';
  const isRequesting = props.state === 'requesting_permission';
  const effectiveState = props.result?.state ?? props.pipelineState;

  return (
    <div className="relative flex min-h-[calc(100dvh-100px)] select-none flex-col items-center justify-between px-4 py-6">
      <div className="flex h-8 items-center justify-center">
        {props.detectedLanguage && props.detectedLanguage !== 'unknown' && <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-cyan-300">Detected: {getLanguageDisplayLabel(props.detectedLanguage)}</div>}
      </div>

      <div className={`my-auto flex w-full max-w-5xl flex-col items-center justify-center py-4 text-center ${isRecording ? '-translate-y-4 space-y-4' : 'space-y-6'}`}>
        <VoiceOrb state={props.state} audioLevel={props.audioLevel} disabled={!props.canSubmit || isProcessing || isRequesting || props.state === 'terminal'} onClick={isRecording ? props.onStopAndAsk : props.onStartRecording} />

        {effectiveState && !props.result && <div className="w-full max-w-2xl"><PipelineStepper state={effectiveState} /></div>}

        <div className="flex min-h-[100px] w-full flex-col items-center justify-center space-y-3 px-4 pb-3">
          {isRecording ? <><h2 className="text-3xl font-bold text-white">Listening…</h2><p className="max-w-xl text-base leading-relaxed text-cyan-300">{props.partialTranscript || 'Speak your complete question.'}</p><span className="text-[10px] text-slate-500">Live draft — auto-stops after 1.5 seconds of silence</span></> :
            isRequesting ? <><h2 className="text-2xl font-bold text-white">Requesting microphone…</h2><p className="text-xs text-slate-400">Allow microphone access in the browser prompt.</p></> :
            isProcessing ? <><h2 className="text-2xl font-bold text-white">{effectiveState ? PIPELINE_STATE_TO_USER_STATUS[effectiveState] : 'Processing…'}</h2><p className="text-xs text-slate-400">Searching the verified MSMARCO-XI evidence index.</p></> :
            props.result ? (
              <AnswerCards
                result={props.result}
                synthesisLoading={props.synthesisLoading}
                synthesisResult={props.synthesisResult}
                synthesisError={props.synthesisError}
                onDismiss={props.onReset}
              />
            ) : <><h2 className="text-3xl font-bold text-white">Ask with voice or text</h2><p className="text-sm text-slate-400">Validated corpus paths: English, Hindi, and Hinglish. Other provider languages remain experimental.</p><div className="flex flex-wrap justify-center gap-2 pt-2">{SAMPLE_PROMPTS.map((prompt) => <button key={prompt.text} type="button" disabled={!props.canSubmit} onClick={() => props.onSelectSamplePrompt(prompt.text)} className="max-w-[280px] truncate rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs text-slate-300 disabled:opacity-40"><span className="mr-1.5 font-mono text-[10px] text-cyan-400">[{prompt.label}]</span>{prompt.text}</button>)}</div></>}

          {props.error && !props.result && <div className="max-w-md rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">{props.error.message}</div>}
          {!props.canSubmit && !props.result && <button type="button" onClick={props.onOpenDiagnostics} className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">Backend not ready — view checks</button>}
        </div>
      </div>

      <VoicePillControls {...props} state={props.state} onSelectSamplePrompt={props.onSelectSamplePrompt} />
    </div>
  );
};
