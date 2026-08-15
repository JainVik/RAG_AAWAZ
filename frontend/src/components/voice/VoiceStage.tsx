import React, { useState } from 'react';
import {
  Quotes,
  Copy,
  Check,
  Lightning,
  Sparkle,
  HandPalm,
  WarningOctagon,
} from '@phosphor-icons/react';
import type { LanguageHint, QueryResponse, VoiceState, VoiceErrorState } from '../../types/api';
import { VoiceOrb } from './VoiceOrb';
import { VoicePillControls } from './VoicePillControls';
import { CitationDrawer } from '../citations/CitationDrawer';

interface VoiceStageProps {
  state: VoiceState;
  error: VoiceErrorState | null;
  recordingDuration: number;
  audioLevel: number;
  selectedLanguage: LanguageHint;
  detectedLanguage: string | null;
  partialTranscript: string;
  result: QueryResponse | null;
  onLanguageChange: (lang: LanguageHint) => void;
  onStartRecording: () => void;
  onStopAndAsk: () => void;
  onCancelRecording: () => void;
  onReset: () => void;
  onToggleTextMode: () => void;
  onSelectSamplePrompt: (prompt: string) => void;
  onOpenDiagnostics?: () => void;
}

export const VoiceStage: React.FC<VoiceStageProps> = ({
  state,
  error,
  recordingDuration,
  audioLevel,
  selectedLanguage,
  detectedLanguage,
  partialTranscript,
  result,
  onLanguageChange,
  onStartRecording,
  onStopAndAsk,
  onCancelRecording,
  onReset,
  onToggleTextMode,
  onSelectSamplePrompt,
  onOpenDiagnostics,
}) => {
  const [isCitationDrawerOpen, setIsCitationDrawerOpen] = useState(false);
  const [copiedAnswer, setCopiedAnswer] = useState(false);

  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';
  const isRequesting = state === 'requesting_permission';

  const handleCopyAnswer = () => {
    if (result?.answer_text) {
      navigator.clipboard.writeText(result.answer_text);
      setCopiedAnswer(true);
      setTimeout(() => setCopiedAnswer(false), 1500);
    }
  };

  const samplePrompts = [
    { text: 'गोवा सरकारची जलसंधारण योजना काय आहे?', label: 'मराठी' },
    { text: 'मुख्यमंत्री रोजगार योजना के लिए क्या पात्रता है?', label: 'हिंदी' },
    { text: 'What is the procedure for obtaining a revenue certificate in Goa?', label: 'English' },
  ];

  return (
    <div className="relative min-h-[calc(100dvh-100px)] flex flex-col items-center justify-between py-6 px-4 select-none">
      {/* Top Spacer / Detected Language pill */}
      <div className="h-8 flex items-center justify-center">
        {detectedLanguage && detectedLanguage !== 'unknown' && (
          <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-white/5 border border-white/10 backdrop-blur-md rounded-full text-[11px] font-mono font-semibold text-cyan-300 shadow-sm animate-fade-in">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
            <span>Detected Language: {detectedLanguage.toUpperCase()}</span>
          </div>
        )}
      </div>

      {/* Main Center Stage with Generous Breathing Room */}
      <div className="flex flex-col items-center justify-center max-w-2xl mx-auto w-full my-auto text-center space-y-8 py-4">
        {/* Dynamic Glowing Voice Orb */}
        <VoiceOrb
          state={state}
          audioLevel={audioLevel}
          onClick={isRecording ? onStopAndAsk : onStartRecording}
        />

        {/* Dynamic Text / Speech Feedback */}
        <div className="space-y-3 px-4 min-h-[100px] flex flex-col items-center justify-center">
          {isRecording ? (
            <div className="space-y-2 animate-fade-in">
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white headline-display">
                I&apos;m listening...
              </h2>
              <p className="text-base text-cyan-300 font-medium max-w-lg leading-relaxed">
                {partialTranscript || 'What is on your mind?'}
              </p>
            </div>
          ) : isRequesting ? (
            <div className="space-y-1">
              <h2 className="text-2xl font-bold text-white">
                Requesting microphone...
              </h2>
              <p className="text-xs text-slate-400">
                Please allow microphone access in your browser prompt.
              </p>
            </div>
          ) : isProcessing ? (
            <div className="space-y-1">
              <h2 className="text-2xl font-bold text-white">
                Processing your question...
              </h2>
              <p className="text-xs text-slate-400">
                Transcribing audio &amp; searching verified Goa Governance Index.
              </p>
            </div>
          ) : result ? (
            <div className="space-y-4 max-w-xl text-left bg-[#0e1529]/90 border border-cyan-500/30 backdrop-blur-xl p-6 rounded-2xl shadow-2xl animate-fade-in">
              {/* Question Transcript Header */}
              {result.transcript && (
                <div className="pb-3 border-b border-white/10 flex items-center justify-between text-xs text-slate-400">
                  <span className="font-semibold text-cyan-400 flex items-center gap-1.5">
                    <Sparkle size={14} weight="fill" />
                    <span>Query Transcript:</span>
                  </span>
                  {result.timings_ms?.total_duration_ms && (
                    <span className="font-mono text-[11px] text-slate-400 flex items-center gap-1">
                      <Lightning size={13} className="text-cyan-400" />
                      <span>{result.timings_ms.total_duration_ms} ms</span>
                    </span>
                  )}
                </div>
              )}

              {result.transcript && (
                <p className="text-xs text-slate-300 italic">
                  &ldquo;{result.transcript}&rdquo;
                </p>
              )}

              {/* Answer Text */}
              {result.answer_text ? (
                <p className="text-base text-white leading-relaxed font-sans font-normal">
                  {result.answer_text}
                </p>
              ) : result.guardrail?.decision === 'abstain' ? (
                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-center gap-2.5">
                  <HandPalm size={18} weight="fill" />
                  <span>
                    {result.guardrail.user_message ||
                      'Truthful Abstention: The corpus does not contain enough verified evidence for this question.'}
                  </span>
                </div>
              ) : (
                <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2.5">
                  <WarningOctagon size={18} weight="fill" />
                  <span>{result.error?.message || 'Unable to complete answer.'}</span>
                </div>
              )}

              {/* Citation & Copy Actions */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-white/10">
                {result.citations && result.citations.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => setIsCitationDrawerOpen(true)}
                    className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 text-xs font-semibold transition-all cursor-pointer"
                  >
                    <Quotes size={15} weight="fill" />
                    <span>View {result.citations.length} Grounded Citations</span>
                  </button>
                ) : (
                  <span className="text-[11px] text-slate-500 font-mono">0 citations</span>
                )}

                {result.answer_text && (
                  <button
                    type="button"
                    onClick={handleCopyAnswer}
                    className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors cursor-pointer"
                  >
                    {copiedAnswer ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                    <span>{copiedAnswer ? 'Copied' : 'Copy answer'}</span>
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white headline-display">
                I&apos;m listening...
              </h2>
              <p className="text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
                What is on your mind? Speak in English, हिंदी, or मराठी.
              </p>

              {/* Sample Prompts Chips with proper vertical spacing and breathing room */}
              <div className="flex flex-wrap items-center justify-center gap-2.5 pt-3 mb-4">
                {samplePrompts.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => onSelectSamplePrompt(p.text)}
                    className="px-3.5 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-cyan-400/40 rounded-full text-xs text-slate-300 hover:text-white transition-all cursor-pointer truncate max-w-[280px] shadow-sm"
                  >
                    <span className="text-cyan-400 font-mono text-[10px] mr-1.5">[{p.label}]</span>
                    <span>{p.text}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Error Banner */}
          {error && !result && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs text-center max-w-md">
              {error.message}
            </div>
          )}
        </div>
      </div>

      {/* Floating Bottom Slim Dock with Clean Lower Margin */}
      <div className="w-full flex justify-center pt-6 pb-4">
        <VoicePillControls
          state={state}
          selectedLanguage={selectedLanguage}
          recordingDuration={recordingDuration}
          onLanguageChange={onLanguageChange}
          onStartRecording={onStartRecording}
          onStopAndAsk={onStopAndAsk}
          onCancelRecording={onCancelRecording}
          onReset={onReset}
          onToggleTextMode={onToggleTextMode}
          onSelectSamplePrompt={onSelectSamplePrompt}
          onOpenDiagnostics={onOpenDiagnostics}
        />
      </div>

      {/* Citations & Evidence Inspector Drawer */}
      <CitationDrawer
        isOpen={isCitationDrawerOpen}
        onClose={() => setIsCitationDrawerOpen(false)}
        result={result}
      />
    </div>
  );
};
