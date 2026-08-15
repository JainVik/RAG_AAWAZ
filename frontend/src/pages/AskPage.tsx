import React, { useState } from 'react';
import { X, TextT, WarningCircle } from '@phosphor-icons/react';
import type { VoiceResultData } from '../types/api';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { VoiceStage } from '../components/voice/VoiceStage';
import { TextInputPanel } from '../components/text/TextInputPanel';
import { sendTextQuery } from '../services/api';
import { useShell } from '../components/layout/Shell';

export const AskPage: React.FC = () => {
  const [showTextModal, setShowTextModal] = useState<boolean>(false);
  const [textError, setTextError] = useState<string | null>(null);
  const [textResult, setTextResult] = useState<VoiceResultData | null>(null);
  const { openSystemChecks } = useShell();

  // Text mode execution state
  const [isTextLoading, setIsTextLoading] = useState<boolean>(false);

  // Voice mode state & WebSocket engine
  const {
    state: voiceState,
    error: voiceError,
    recordingDuration,
    audioLevel,
    partialTranscript,
    detectedLanguage,
    result: voiceResult,
    selectedLanguage,
    setSelectedLanguage,
    startRecording,
    stopAndAsk,
    cancelRecording,
    resetToIdle,
  } = useVoiceRecorder();

  // Unified active result (voice or text)
  const activeResult = textResult || voiceResult;

  // Handle Text Mode Submission
  const handleTextSubmit = async (queryText: string) => {
    setIsTextLoading(true);
    setTextError(null);
    const requestId = `txt_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;

    try {
      const response = await sendTextQuery({
        query: queryText,
        language: selectedLanguage,
        request_id: requestId,
        deadline_ms: null,
      });

      setShowTextModal(false);

      // Map QueryResponse into VoiceResultData display format
      const formattedResult: VoiceResultData = {
        request_id: response.request_id || requestId,
        state: response.state || 'COMPLETED',
        answer_mode: response.answer_mode || 'grounded_extractive',
        transcript: response.transcript || queryText,
        language: response.language || (selectedLanguage as string),
        answer_text: response.answer_text || response.answer || null,
        abstention_reason: response.abstention_reason || null,
        guardrail: response.guardrail || undefined,
        citations: response.citations || [],
        timings: response.timings || {
          audio_received_ms: 0,
          stt_final_ms: 0,
          retrieval_ms: 0,
          answer_ms: 0,
          total_ms: 0,
        },
      };

      setTextResult(formattedResult);
    } catch (err) {
      setTextError(
        err instanceof Error
          ? err.message
          : 'Backend query failed. Please ensure FastAPI server is running on 127.0.0.1:8000.'
      );
    } finally {
      setIsTextLoading(false);
    }
  };

  const handleReset = () => {
    setTextResult(null);
    setTextError(null);
    resetToIdle();
  };

  return (
    <div className="w-full flex-1 flex flex-col justify-between">
      {/* Central Immersive Voice Stage */}
      <VoiceStage
        state={voiceState}
        error={voiceError}
        recordingDuration={recordingDuration}
        audioLevel={audioLevel}
        selectedLanguage={selectedLanguage}
        detectedLanguage={detectedLanguage}
        partialTranscript={partialTranscript}
        result={activeResult}
        onLanguageChange={setSelectedLanguage}
        onStartRecording={startRecording}
        onStopAndAsk={stopAndAsk}
        onCancelRecording={cancelRecording}
        onReset={handleReset}
        onToggleTextMode={() => {
          setTextError(null);
          setShowTextModal(true);
        }}
        onOpenDiagnostics={openSystemChecks}
        onSelectSamplePrompt={(prompt) => {
          setShowTextModal(true);
          handleTextSubmit(prompt);
        }}
      />

      {/* Text Test Mode Modal Overlay */}
      {showTextModal && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md"
        >
          <div className="w-full max-w-2xl bg-[#0e1424] border border-white/12 rounded-2xl shadow-2xl overflow-hidden animate-fade-in space-y-0">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-xs">
                <TextT size={18} />
                <span>Text Test Mode (Real Direct Backend Query)</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowTextModal(false);
                  setTextError(null);
                }}
                className="p-1 rounded-lg text-slate-400 hover:text-white transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              {textError && (
                <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-300 flex items-start gap-2.5">
                  <WarningCircle size={18} className="shrink-0 mt-0.5" />
                  <div className="space-y-0.5">
                    <span className="font-bold block">Backend Request Failed:</span>
                    <p className="leading-relaxed font-mono text-[11px]">{textError}</p>
                  </div>
                </div>
              )}

              <TextInputPanel
                isLoading={isTextLoading}
                selectedLanguage={selectedLanguage}
                onLanguageChange={setSelectedLanguage}
                onSubmit={handleTextSubmit}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
