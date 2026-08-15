import React, { useState } from 'react';
import {
  Microphone,
  Stop,
  X,
  CircleNotch,
  Globe,
  TextT,
  ArrowCounterClockwise,
  Sparkle,
  ShieldCheck,
  Check,
  CaretUp,
} from '@phosphor-icons/react';
import type { LanguageHint, VoiceState } from '../../types/api';
import { LANGUAGE_REGISTRY } from '../../types/api';

interface VoicePillControlsProps {
  state: VoiceState;
  selectedLanguage: LanguageHint;
  recordingDuration: number;
  onLanguageChange: (lang: LanguageHint) => void;
  onStartRecording: () => void;
  onStopAndAsk: () => void;
  onCancelRecording: () => void;
  onReset: () => void;
  onToggleTextMode: () => void;
  onSelectSamplePrompt: (prompt: string) => void;
  onOpenDiagnostics?: () => void;
}

export const VoicePillControls: React.FC<VoicePillControlsProps> = ({
  state,
  selectedLanguage,
  recordingDuration,
  onLanguageChange,
  onStartRecording,
  onStopAndAsk,
  onCancelRecording,
  onReset,
  onToggleTextMode,
  onSelectSamplePrompt,
  onOpenDiagnostics,
}) => {
  const [isLangHovered, setIsLangHovered] = useState(false);
  const [isExamplesHovered, setIsExamplesHovered] = useState(false);
  const [isModeHovered, setIsModeHovered] = useState(false);

  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';
  const isRequesting = state === 'requesting_permission';
  const isTerminal = state === 'terminal';

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const samplePrompts = [
    { text: 'गोवा सरकारची जलसंधारण योजना काय आहे?', label: 'मराठी', cat: 'Water Policy' },
    { text: 'मुख्यमंत्री रोजगार योजना के लिए क्या पात्रता है?', label: 'हिंदी', cat: 'Employment' },
    { text: 'What is the procedure for obtaining a revenue certificate in Goa?', label: 'English', cat: 'Revenue' },
    { text: 'माहिती अधिकार कायद्यानुसार अर्ज कसा करावा?', label: 'मराठी', cat: 'RTI Act' },
  ];

  const currentLangObj = LANGUAGE_REGISTRY.find((l) => l.code === selectedLanguage) || LANGUAGE_REGISTRY[0];

  const validatedLanguages = LANGUAGE_REGISTRY.filter((l) => l.validated);
  const experimentalLanguages = LANGUAGE_REGISTRY.filter((l) => !l.validated);

  return (
    <div className="relative flex flex-col items-center select-none">
      {/* Recording Duration Floating Badge */}
      {isRecording && (
        <div className="absolute bottom-full mb-3 inline-flex items-center gap-2 px-3.5 py-1 bg-cyan-500/10 border border-cyan-400/30 backdrop-blur-md rounded-full text-[11px] font-mono font-bold text-cyan-300 shadow-xl animate-pulse z-30">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
          <span>Listening: {formatTime(recordingDuration)} / 1:00</span>
        </div>
      )}

      {/* Floating Hover Tray 1: Language Selection Menu (16 Indic Languages Registry) */}
      {isLangHovered && (
        <div
          onMouseEnter={() => setIsLangHovered(true)}
          onMouseLeave={() => setIsLangHovered(false)}
          className="absolute bottom-full mb-3 w-80 max-h-80 overflow-y-auto bg-[#0e1424]/95 backdrop-blur-2xl border border-white/15 rounded-2xl p-2.5 shadow-2xl z-30 animate-fade-in space-y-2"
        >
          {/* Header */}
          <div className="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between border-b border-white/10 pb-1.5">
            <span>Spoken Language Hint</span>
            <span className="text-[9px] font-mono text-cyan-400">16 Indic Enums</span>
          </div>

          {/* Validated Corpus Languages */}
          <div>
            <div className="px-2 py-0.5 text-[9px] font-bold text-emerald-400 uppercase tracking-wider">
              Validated Corpus Languages
            </div>
            <div className="space-y-1 mt-1">
              {validatedLanguages.map((opt) => (
                <button
                  key={opt.code}
                  type="button"
                  onClick={() => {
                    onLanguageChange(opt.code);
                    setIsLangHovered(false);
                  }}
                  className={`w-full p-2 rounded-xl text-left flex items-center justify-between transition-colors cursor-pointer text-xs ${
                    selectedLanguage === opt.code
                      ? 'bg-blue-600/20 text-cyan-300 border border-cyan-400/30 font-semibold'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">{opt.nativeLabel}</span>
                    <span className="text-[10px] text-slate-400">({opt.label})</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      Validated
                    </span>
                    {selectedLanguage === opt.code && <Check size={14} className="text-cyan-400 shrink-0" />}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Experimental / Not Benchmarked Languages */}
          <div>
            <div className="px-2 py-0.5 text-[9px] font-bold text-amber-400/90 uppercase tracking-wider">
              Accepted by API (Not benchmarked)
            </div>
            <div className="space-y-1 mt-1">
              {experimentalLanguages.map((opt) => (
                <button
                  key={opt.code}
                  type="button"
                  onClick={() => {
                    onLanguageChange(opt.code);
                    setIsLangHovered(false);
                  }}
                  className={`w-full p-1.5 px-2 rounded-xl text-left flex items-center justify-between transition-colors cursor-pointer text-xs ${
                    selectedLanguage === opt.code
                      ? 'bg-blue-600/20 text-cyan-300 border border-cyan-400/30 font-semibold'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">{opt.nativeLabel}</span>
                    <span className="text-[10px] text-slate-400">({opt.label})</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-white/5 text-slate-400 border border-white/10">
                      Experimental
                    </span>
                    {selectedLanguage === opt.code && <Check size={14} className="text-cyan-400 shrink-0" />}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Floating Hover Tray 2: Instant Examples Menu */}
      {isExamplesHovered && (
        <div
          onMouseEnter={() => setIsExamplesHovered(true)}
          onMouseLeave={() => setIsExamplesHovered(false)}
          className="absolute bottom-full mb-3 w-80 sm:w-96 bg-[#0e1424]/95 backdrop-blur-2xl border border-white/15 rounded-2xl p-3 shadow-2xl z-30 animate-fade-in space-y-2"
        >
          <div className="flex items-center justify-between text-[10px] font-bold text-slate-400 uppercase tracking-wider px-1">
            <span className="flex items-center gap-1">
              <Sparkle size={12} className="text-cyan-400" />
              <span>Sample Governance Questions</span>
            </span>
            <span className="text-[9px] text-slate-500 font-mono">Click to ask</span>
          </div>
          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
            {samplePrompts.map((p, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  onSelectSamplePrompt(p.text);
                  setIsExamplesHovered(false);
                }}
                className="w-full p-2.5 rounded-xl bg-white/5 hover:bg-white/10 hover:border-cyan-400/40 border border-white/5 text-left transition-all cursor-pointer group"
              >
                <div className="flex items-center justify-between text-[10px] font-mono mb-1">
                  <span className="text-cyan-400 font-bold">{p.label}</span>
                  <span className="text-slate-500">{p.cat}</span>
                </div>
                <p className="text-xs text-slate-200 group-hover:text-white line-clamp-2 leading-relaxed">
                  {p.text}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Floating Hover Tray 3: Input Mode Switcher Menu */}
      {isModeHovered && (
        <div
          onMouseEnter={() => setIsModeHovered(true)}
          onMouseLeave={() => setIsModeHovered(false)}
          className="absolute bottom-full mb-3 w-56 bg-[#0e1424]/95 backdrop-blur-2xl border border-white/15 rounded-2xl p-2 shadow-2xl z-30 animate-fade-in space-y-1"
        >
          <div className="px-2.5 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            Input Mode
          </div>
          <button
            type="button"
            onClick={() => {
              if (state === 'idle') onStartRecording();
              setIsModeHovered(false);
            }}
            className="w-full p-2 rounded-xl text-left flex items-center gap-2.5 bg-blue-600/20 text-cyan-300 border border-cyan-400/30 text-xs font-semibold"
          >
            <Microphone size={16} />
            <div>
              <span>Voice Mode (Primary)</span>
              <span className="text-[10px] text-slate-400 block font-normal">Realtime 16kHz PCM Stream</span>
            </div>
          </button>
          <button
            type="button"
            onClick={() => {
              onToggleTextMode();
              setIsModeHovered(false);
            }}
            className="w-full p-2 rounded-xl text-left flex items-center gap-2.5 text-slate-300 hover:bg-white/5 hover:text-white transition-colors cursor-pointer text-xs"
          >
            <TextT size={16} />
            <div>
              <span>Text Test Mode</span>
              <span className="text-[10px] text-slate-400 block font-normal">4,096 char deterministic input</span>
            </div>
          </button>
        </div>
      )}

      {/* SLIM REFINED DOCK BAR */}
      <div className="h-12 px-3 bg-[#0a0f1d]/90 hover:bg-[#0a0f1d] backdrop-blur-2xl border border-white/12 rounded-full shadow-[0_12px_40px_rgba(0,0,0,0.7)] flex items-center gap-1.5 transition-all duration-300">
        {/* GROUP 1: Mode Selector (Hover Reveal) */}
        <div
          className="relative"
          onMouseEnter={() => setIsModeHovered(true)}
          onMouseLeave={() => setIsModeHovered(false)}
        >
          <button
            type="button"
            onClick={onToggleTextMode}
            className="h-9 px-2.5 rounded-full bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/8 flex items-center gap-1.5 text-xs font-medium transition-all cursor-pointer"
            title="Input Mode Options"
          >
            <Microphone size={15} className="text-cyan-400" weight="bold" />
            <span className="hidden sm:inline text-[11px]">Voice</span>
            <CaretUp size={11} className="text-slate-500" />
          </button>
        </div>

        {/* GROUP 2: Quick Examples Tray Button (Hover Reveal) */}
        <div
          className="relative"
          onMouseEnter={() => setIsExamplesHovered(true)}
          onMouseLeave={() => setIsExamplesHovered(false)}
        >
          <button
            type="button"
            onClick={() => setIsExamplesHovered(!isExamplesHovered)}
            className="h-9 px-2.5 rounded-full bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/8 flex items-center gap-1.5 text-xs font-medium transition-all cursor-pointer"
            title="Sample Governance Questions"
          >
            <Sparkle size={15} className="text-cyan-400" />
            <span className="hidden sm:inline text-[11px]">Examples</span>
            <CaretUp size={11} className="text-slate-500" />
          </button>
        </div>

        {/* Divider */}
        <div className="h-5 w-[1px] bg-white/10 mx-1" />

        {/* GROUP 3: Central Core Actions (Cancel / Glowing Mic / Reset) */}
        <div className="flex items-center gap-1.5">
          {/* Cancel or Reset Button */}
          {(isRecording || isRequesting || isProcessing || isTerminal) && (
            <button
              type="button"
              onClick={isTerminal ? onReset : onCancelRecording}
              className="w-9 h-9 rounded-full bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/10 flex items-center justify-center transition-all cursor-pointer active:scale-95"
              title={isTerminal ? 'Reset conversation' : 'Cancel request'}
            >
              {isTerminal ? <ArrowCounterClockwise size={15} /> : <X size={15} />}
            </button>
          )}

          {/* Primary Action Button */}
          {isRecording ? (
            <button
              type="button"
              onClick={onStopAndAsk}
              className="h-9 px-4 rounded-full bg-gradient-to-tr from-rose-600 to-rose-500 text-white shadow-[0_0_20px_rgba(225,29,72,0.6)] flex items-center gap-1.5 text-xs font-bold transition-all cursor-pointer transform hover:scale-105 active:scale-95"
              title="Stop and get answer"
            >
              <Stop size={16} weight="fill" />
              <span>Stop &amp; Ask</span>
            </button>
          ) : isRequesting || isProcessing ? (
            <button
              type="button"
              disabled
              className="h-9 px-4 rounded-full bg-blue-600/40 text-cyan-200 border border-cyan-400/30 flex items-center gap-1.5 text-xs font-medium cursor-not-allowed opacity-80"
            >
              <CircleNotch size={15} className="animate-spin" />
              <span>{isRequesting ? 'Connecting' : 'Thinking'}</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onStartRecording}
              className="h-9 px-4 rounded-full bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white shadow-[0_0_20px_rgba(37,99,235,0.5)] hover:shadow-[0_0_30px_rgba(6,182,212,0.7)] flex items-center gap-1.5 text-xs font-bold transition-all cursor-pointer transform hover:scale-105 active:scale-95"
              title="Start recording"
            >
              <Microphone size={16} weight="bold" />
              <span>Speak</span>
            </button>
          )}
        </div>

        {/* Divider */}
        <div className="h-5 w-[1px] bg-white/10 mx-1" />

        {/* GROUP 4: Language Selector (Hover Reveal) */}
        <div
          className="relative"
          onMouseEnter={() => setIsLangHovered(true)}
          onMouseLeave={() => setIsLangHovered(false)}
        >
          <button
            type="button"
            onClick={() => setIsLangHovered(!isLangHovered)}
            disabled={isRecording || isProcessing}
            className="h-9 px-2.5 rounded-full bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white border border-white/8 flex items-center gap-1.5 text-xs font-medium transition-all cursor-pointer disabled:opacity-50"
            title="Spoken Language Configuration"
          >
            <Globe size={15} className="text-cyan-400" />
            <span className="font-mono text-[11px] uppercase">
              {currentLangObj.nativeLabel}
            </span>
            <CaretUp size={11} className="text-slate-500" />
          </button>
        </div>

        {/* GROUP 5: Diagnostics Quick Trigger */}
        {onOpenDiagnostics && (
          <button
            type="button"
            onClick={onOpenDiagnostics}
            className="w-9 h-9 rounded-full bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white border border-white/8 flex items-center justify-center transition-all cursor-pointer"
            title="System Diagnostics & Readiness"
          >
            <ShieldCheck size={16} />
          </button>
        )}
      </div>
    </div>
  );
};
