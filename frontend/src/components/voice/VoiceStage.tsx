import React from 'react';
import type {
  LanguageHint,
  PipelineState,
  QueryResponse,
  ServerLanguageCode,
  SynthesisResponse,
  VerifiedPromptCatalog,
  VoiceErrorState,
  VoiceState,
} from '../../types/api';
import { PIPELINE_STATE_TO_USER_STATUS } from '../../types/api';
import type { SessionQueryHistoryEntry } from '../../utils/sessionQueryHistory';
import type { ChatTurn } from '../../utils/chatSessionHistory';
import { VoiceOrb } from './VoiceOrb';
import { VoicePillControls } from './VoicePillControls';
import { PipelineStepper } from '../pipeline/PipelineStepper';
import { AnswerCards } from './AnswerCards';
import { ChatTimeline } from '../chat/ChatTimeline';

interface VoiceStageProps {
  state: VoiceState;
  textSubmitting: boolean;
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
  verifiedPromptCatalog: VerifiedPromptCatalog | null;
  verifiedPromptsLoading: boolean;
  verifiedPromptsError: string | null;
  recentQueries: SessionQueryHistoryEntry[];
  chatTurns: ChatTurn[];
  onLanguageChange: (language: LanguageHint) => void;
  onStartRecording: () => void;
  onStopAndAsk: () => void;
  onCancelRecording: () => void;
  onReset: () => void;
  onClearSession: () => void;
  onToggleTextMode: () => void;
  onSelectVerifiedPrompt: (prompt: string, language: ServerLanguageCode) => void;
  onRetryVerifiedPrompts: () => void;
  onClearRecentQueries: () => void;
  onOpenDiagnostics?: () => void;
}

export const VoiceStage: React.FC<VoiceStageProps> = (props) => {
  const isRecording = props.state === 'recording';
  const isVoiceProcessing = props.state === 'processing';
  const isProcessing = isVoiceProcessing || props.textSubmitting;
  const isRequesting = props.state === 'requesting_permission';
  const effectiveState = props.result?.state ?? props.pipelineState;
  const isLive = isRecording || isProcessing || isRequesting;

  const hasChatHistory = props.chatTurns.length > 0;
  const hasActiveConversation = hasChatHistory || isLive || Boolean(props.result);

  return (
    <div className="relative flex min-h-[calc(100dvh-100px)] select-none flex-col items-center justify-between px-2 sm:px-4 py-2">
      {/* CONDITIONAL BODY: Hero Landing (0 turns) vs Chat Timeline Stream (>= 1 turn) */}
      {!hasChatHistory ? (
        /* HERO INITIAL STATE */
        <div
          className={`mt-6 mb-auto flex w-full max-w-5xl flex-col items-center justify-center py-4 text-center transition-all duration-500 ${
            isRecording ? '-translate-y-4 space-y-4' : 'space-y-6'
          }`}
        >
          <VoiceOrb
            state={props.textSubmitting ? 'processing' : props.state}
            audioLevel={props.audioLevel}
            disabled={!props.canSubmit || isProcessing || isRequesting || props.state === 'terminal'}
            onClick={isRecording ? props.onStopAndAsk : props.onStartRecording}
          />

          {effectiveState && !props.result && (
            <div className="w-full max-w-2xl">
              <PipelineStepper state={effectiveState} />
            </div>
          )}

          <div className="flex min-h-[100px] w-full flex-col items-center justify-center space-y-3 px-4 pb-3">
            {isRecording ? (
              <>
                <h2 className="text-3xl font-bold text-white">Listening…</h2>
                <p className="max-w-xl text-base leading-relaxed text-cyan-300 font-medium">
                  {props.partialTranscript || 'Speak your complete question.'}
                </p>
                <span className="text-[10px] text-slate-500">Live draft — auto-stops after 1.5 seconds of silence</span>
              </>
            ) : isRequesting ? (
              <>
                <h2 className="text-2xl font-bold text-white">Requesting microphone…</h2>
                <p className="text-xs text-slate-400">Allow microphone access in the browser prompt.</p>
              </>
            ) : isProcessing ? (
              <>
                <h2 className="text-2xl font-bold text-white">
                  {effectiveState ? PIPELINE_STATE_TO_USER_STATUS[effectiveState] : 'Processing…'}
                </h2>
                <p className="text-xs text-slate-400">Searching the verified MSMARCO-XI evidence index.</p>
              </>
            ) : props.result ? (
              <AnswerCards
                result={props.result}
                synthesisLoading={props.synthesisLoading}
                synthesisResult={props.synthesisResult}
                synthesisError={props.synthesisError}
                onDismiss={props.onReset}
              />
            ) : (
              <h2 className="text-3xl font-bold text-white">Ask with voice or text</h2>
            )}

            {props.error && !props.result && (
              <div className="max-w-md rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
                {props.error.message}
              </div>
            )}
            {!props.canSubmit && !props.result && (
              <button
                type="button"
                onClick={props.onOpenDiagnostics}
                className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200"
              >
                Backend not ready — view checks
              </button>
            )}
          </div>
        </div>
      ) : (
        /* CHAT TIMELINE STREAM (>= 1 turn) */
        <div className="w-full flex-1 flex flex-col justify-start">
          <ChatTimeline
            turns={props.chatTurns}
            liveQuery={props.partialTranscript}
            liveState={props.textSubmitting ? 'processing' : props.state}
            isLive={isLive}
            audioLevel={props.audioLevel}
          />
        </div>
      )}

      {/* Fixed bottom controls overlay the page's normal document flow. */}
      <div className="fixed bottom-4 left-0 right-0 z-40 flex justify-center pointer-events-none px-2 sm:px-4">
        <div className="pointer-events-auto">
          <VoicePillControls
            state={props.state}
            textSubmitting={props.textSubmitting}
            canSubmit={props.canSubmit}
            selectedLanguage={props.selectedLanguage}
            recordingDuration={props.recordingDuration}
            onLanguageChange={props.onLanguageChange}
            onStartRecording={props.onStartRecording}
            onStopAndAsk={props.onStopAndAsk}
            onCancelRecording={props.onCancelRecording}
            onReset={props.onReset}
            onToggleTextMode={props.onToggleTextMode}
            verifiedPromptCatalog={props.verifiedPromptCatalog}
            verifiedPromptsLoading={props.verifiedPromptsLoading}
            verifiedPromptsError={props.verifiedPromptsError}
            recentQueries={props.recentQueries}
            showQuickPrompts={!hasActiveConversation}
            showNewConversation={hasActiveConversation}
            onClearSession={props.onClearSession}
            onSelectVerifiedPrompt={props.onSelectVerifiedPrompt}
            onRetryVerifiedPrompts={props.onRetryVerifiedPrompts}
            onClearRecentQueries={props.onClearRecentQueries}
          />
        </div>
      </div>
    </div>
  );
};
