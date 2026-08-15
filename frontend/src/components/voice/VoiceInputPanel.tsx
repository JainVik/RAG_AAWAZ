import React from 'react';
import {
  Microphone,
  Stop,
  X,
  CircleNotch,
  ArrowCounterClockwise,
  Globe,
  WarningOctagon,
  TextT,
} from '@phosphor-icons/react';
import type { LanguageHint, VoiceState, VoiceErrorState } from '../../types/api';
import { AudioWaveform } from './AudioWaveform';

interface VoiceInputPanelProps {
  state: VoiceState;
  error: VoiceErrorState | null;
  recordingDuration: number;
  audioLevel: number;
  selectedLanguage: LanguageHint;
  onLanguageChange: (lang: LanguageHint) => void;
  onStartRecording: () => void;
  onStopAndAsk: () => void;
  onCancelRecording: () => void;
  onReset: () => void;
  onSwitchToText: () => void;
}

export const VoiceInputPanel: React.FC<VoiceInputPanelProps> = ({
  state,
  error,
  recordingDuration,
  audioLevel,
  selectedLanguage,
  onLanguageChange,
  onStartRecording,
  onStopAndAsk,
  onCancelRecording,
  onReset,
  onSwitchToText,
}) => {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const isRecording = state === 'recording';
  const isRequesting = state === 'requesting_permission';
  const isProcessing = state === 'processing';
  const isTerminal = state === 'terminal';

  return (
    <div className="w-full bg-surface border border-subtle rounded-2xl p-6 sm:p-8 shadow-sm space-y-6">
      {/* Top Bar: Language Hint Selector & Reset */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-subtle">
        {/* Language Hint Selection */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-secondary flex items-center gap-1.5">
            <Globe size={15} className="text-accent-primary" />
            <span>Spoken Language Hint:</span>
          </span>
          <div className="flex items-center gap-1 bg-surface-subtle p-1 rounded-lg border border-subtle">
            {(
              [
                { id: 'unknown', label: 'Auto (Code-mixed)' },
                { id: 'hi', label: 'Hindi' },
                { id: 'en', label: 'English' },
                { id: 'mr', label: 'Marathi' },
              ] as const
            ).map((lang) => (
              <button
                key={lang.id}
                type="button"
                onClick={() => onLanguageChange(lang.id)}
                disabled={isRecording || isProcessing}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all cursor-pointer disabled:opacity-50 ${
                  selectedLanguage === lang.id
                    ? 'bg-surface text-accent-primary shadow-xs font-semibold border border-subtle'
                    : 'text-muted hover:text-primary'
                }`}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </div>

        {/* Reset Conversation Button */}
        {(isTerminal || state !== 'idle') && (
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-primary transition-colors cursor-pointer px-2.5 py-1 rounded-lg hover:bg-surface-subtle"
          >
            <ArrowCounterClockwise size={14} />
            <span>Reset conversation</span>
          </button>
        )}
      </div>

      {/* Main Interaction Area */}
      <div className="flex flex-col items-center justify-center py-6 space-y-6 text-center">
        {/* Waveform / Visualizer */}
        <AudioWaveform level={audioLevel} isRecording={isRecording} />

        {/* State Banner / Timer */}
        <div className="space-y-1">
          {isRecording ? (
            <div className="space-y-1">
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-900 rounded-full text-xs font-semibold">
                <span className="w-2 h-2 rounded-full bg-rose-600 animate-ping" />
                <span>Listening (16kHz PCM Stream)</span>
              </div>
              <div className="font-mono text-xl font-bold text-primary">
                {formatTime(recordingDuration)} <span className="text-muted text-sm font-normal">/ 1:00</span>
              </div>
            </div>
          ) : isRequesting ? (
            <div className="inline-flex items-center gap-2 text-xs font-semibold text-secondary">
              <CircleNotch size={15} className="animate-spin text-accent-primary" />
              <span>Requesting microphone permissions...</span>
            </div>
          ) : isProcessing ? (
            <div className="inline-flex items-center gap-2 text-xs font-semibold text-accent-primary">
              <CircleNotch size={15} className="animate-spin" />
              <span>Transcribing audio &amp; retrieving evidence...</span>
            </div>
          ) : isTerminal ? (
            <span className="text-xs font-semibold text-secondary">
              Question completed. Ready for your next query.
            </span>
          ) : (
            <div className="space-y-0.5">
              <p className="text-sm font-semibold text-primary">
                Click below and speak your question
              </p>
              <p className="text-xs text-muted max-w-sm">
                Supports English, Hindi (हिंदी), Marathi (मराठी), and mixed speech.
              </p>
            </div>
          )}
        </div>

        {/* Primary Record Button Controls */}
        <div className="flex items-center justify-center gap-4">
          {/* Main Action Trigger */}
          {isRecording ? (
            <button
              type="button"
              onClick={onStopAndAsk}
              className="group relative flex items-center gap-2.5 px-6 py-3.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-sm font-bold shadow-md transition-all cursor-pointer transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <Stop size={18} weight="fill" />
              <span>Stop &amp; ask</span>
            </button>
          ) : isRequesting || isProcessing ? (
            <button
              type="button"
              disabled
              className="flex items-center gap-2.5 px-6 py-3.5 bg-surface-subtle border border-subtle text-muted rounded-xl text-sm font-semibold cursor-not-allowed opacity-75"
            >
              <CircleNotch size={18} className="animate-spin text-accent-primary" />
              <span>{isRequesting ? 'Connecting...' : 'Processing...'}</span>
            </button>
          ) : isTerminal ? (
            <button
              type="button"
              onClick={onStartRecording}
              className="flex items-center gap-2.5 px-6 py-3.5 bg-accent-primary hover:bg-accent-hover text-white rounded-xl text-sm font-bold shadow-md transition-all cursor-pointer transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <Microphone size={18} weight="bold" />
              <span>Ask another question</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onStartRecording}
              className="group flex items-center gap-3 px-8 py-4 bg-accent-primary hover:bg-accent-hover text-white rounded-2xl text-base font-bold shadow-lg transition-all cursor-pointer transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <div className="p-1 rounded-lg bg-white/20">
                <Microphone size={22} weight="bold" />
              </div>
              <span>Start recording</span>
            </button>
          )}

          {/* Secondary Control: Cancel / Abort */}
          {(isRecording || isRequesting || isProcessing) && (
            <button
              type="button"
              onClick={onCancelRecording}
              className="inline-flex items-center gap-1.5 px-4 py-3.5 bg-surface border border-subtle text-secondary hover:text-primary hover:bg-surface-subtle rounded-xl text-xs font-semibold transition-all cursor-pointer"
            >
              <X size={16} />
              <span>Cancel</span>
            </button>
          )}
        </div>
      </div>

      {/* Error / Alert Display */}
      {error && (
        <div className="p-4 bg-rose-50/70 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 rounded-xl flex items-start gap-3">
          <WarningOctagon size={20} className="text-rose-600 dark:text-rose-400 mt-0.5 shrink-0" weight="fill" />
          <div className="flex-1 min-w-0">
            <h4 className="text-xs font-bold text-rose-900 dark:text-rose-300">
              {error.type === 'permission_denied'
                ? 'Microphone Permission Required'
                : error.type === 'no_microphone'
                ? 'Microphone Not Found'
                : error.type === 'too_short'
                ? 'Speech Too Short'
                : 'Audio Streaming Error'}
            </h4>
            <p className="text-xs text-rose-700 dark:text-rose-400 mt-0.5 leading-relaxed">
              {error.message}
            </p>
            <div className="mt-3 flex items-center gap-3">
              {error.retryable && (
                <button
                  type="button"
                  onClick={onStartRecording}
                  className="text-xs font-bold text-rose-800 dark:text-rose-200 underline cursor-pointer hover:opacity-80"
                >
                  Try again
                </button>
              )}
              <button
                type="button"
                onClick={onSwitchToText}
                className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 bg-surface border border-subtle rounded-md text-primary hover:bg-surface-subtle transition-colors cursor-pointer"
              >
                <TextT size={13} />
                <span>Switch to Text Test Mode</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
