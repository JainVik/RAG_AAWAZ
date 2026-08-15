import React, { useCallback, useEffect, useRef, useState } from 'react';
import { TextT, WarningCircle, X } from '@phosphor-icons/react';
import type {
  QueryResponse,
  ServerLanguageCode,
  VerifiedPromptCatalog,
} from '../types/api';
import { toBackendLanguage } from '../types/api';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { useSynthesis } from '../hooks/useSynthesis';
import { VoiceStage } from '../components/voice/VoiceStage';
import { TextInputPanel } from '../components/text/TextInputPanel';
import { getVerifiedPrompts, sendTextQuery } from '../services/api';
import { useShell } from '../components/layout/Shell';
import {
  prependSessionQuery,
  readSessionQueryHistory,
  removeSessionQueryHistory,
  toSessionQueryHistoryEntry,
  writeSessionQueryHistory,
} from '../utils/sessionQueryHistory';

export const AskPage: React.FC = () => {
  const [showTextModal, setShowTextModal] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const [textResult, setTextResult] = useState<QueryResponse | null>(null);
  const [isTextLoading, setIsTextLoading] = useState(false);
  const [verifiedPromptCatalog, setVerifiedPromptCatalog] = useState<VerifiedPromptCatalog | null>(null);
  const [verifiedPromptsLoading, setVerifiedPromptsLoading] = useState(true);
  const [verifiedPromptsError, setVerifiedPromptsError] = useState<string | null>(null);
  const [recentQueries, setRecentQueries] = useState(readSessionQueryHistory);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const verifiedPromptsRequestedRef = useRef(false);
  const { openSystemChecks, ready } = useShell();
  const canSubmit = ready?.status === 'ready';
  const voice = useVoiceRecorder();
  const activeResult = textResult ?? voice.result;
  const synthesis = useSynthesis(activeResult);

  const loadVerifiedPromptCatalog = useCallback(async () => {
    setVerifiedPromptsLoading(true);
    setVerifiedPromptsError(null);
    try {
      setVerifiedPromptCatalog(await getVerifiedPrompts());
    } catch (error) {
      setVerifiedPromptCatalog(null);
      setVerifiedPromptsError(
        error instanceof Error ? error.message : 'The verified question gallery is unavailable.',
      );
    } finally {
      setVerifiedPromptsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (verifiedPromptsRequestedRef.current) return;
    verifiedPromptsRequestedRef.current = true;
    void loadVerifiedPromptCatalog();
  }, [loadVerifiedPromptCatalog]);

  useEffect(() => {
    if (!activeResult?.transcript.trim()) return;
    setRecentQueries((current) => {
      const next = prependSessionQuery(current, toSessionQueryHistoryEntry(activeResult));
      writeSessionQueryHistory(next);
      return next;
    });
  }, [activeResult]);

  useEffect(() => {
    if (!showTextModal) return;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowTextModal(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [showTextModal]);

  const handleTextSubmit = async (
    queryText: string,
    languageOverride?: ServerLanguageCode,
  ) => {
    if (!canSubmit) {
      setTextError('The backend is not operationally ready. Open System checks for details.');
      return;
    }
    setTextResult(null);
    voice.resetToIdle();
    setIsTextLoading(true);
    setTextError(null);
    try {
      const response = await sendTextQuery({
        query: queryText,
        language: languageOverride ?? toBackendLanguage(voice.selectedLanguage),
        request_id: crypto.randomUUID(),
        deadline_ms: null,
      });
      setTextResult(response);
      setShowTextModal(false);
    } catch (error) {
      setTextError(error instanceof Error ? error.message : 'The text query failed.');
    } finally {
      setIsTextLoading(false);
    }
  };

  const handleReset = () => {
    setTextResult(null);
    setTextError(null);
    voice.resetToIdle();
  };

  return (
    <div className="flex w-full flex-1 flex-col justify-between">
      <VoiceStage
        state={voice.state}
        textSubmitting={isTextLoading}
        pipelineState={voice.pipelineState}
        error={voice.error}
        recordingDuration={voice.recordingDuration}
        audioLevel={voice.audioLevel}
        selectedLanguage={voice.selectedLanguage}
        detectedLanguage={voice.detectedLanguage}
        partialTranscript={voice.partialTranscript}
        result={activeResult}
        synthesisLoading={synthesis.isLoading}
        synthesisResult={synthesis.result}
        synthesisError={synthesis.error}
        canSubmit={canSubmit}
        verifiedPromptCatalog={verifiedPromptCatalog}
        verifiedPromptsLoading={verifiedPromptsLoading}
        verifiedPromptsError={verifiedPromptsError}
        recentQueries={recentQueries}
        onLanguageChange={voice.setSelectedLanguage}
        onStartRecording={() => {
          setTextResult(null);
          setTextError(null);
          voice.startRecording();
        }}
        onStopAndAsk={voice.stopAndAsk}
        onCancelRecording={voice.cancelRecording}
        onReset={handleReset}
        onToggleTextMode={() => {
          setTextError(null);
          setShowTextModal(true);
        }}
        onOpenDiagnostics={openSystemChecks}
        onSelectVerifiedPrompt={(prompt: string, language: ServerLanguageCode) => {
          setTextError(null);
          setShowTextModal(false);
          void handleTextSubmit(prompt, language);
        }}
        onRetryVerifiedPrompts={() => void loadVerifiedPromptCatalog()}
        onClearRecentQueries={() => {
          setRecentQueries([]);
          removeSessionQueryHistory();
        }}
      />

      {showTextModal && (
        <div role="dialog" aria-modal="true" aria-labelledby="text-dialog-title" className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-md">
          <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-white/12 bg-[#0e1424] shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 p-4">
              <div id="text-dialog-title" className="flex items-center gap-2 text-xs font-bold text-cyan-400"><TextT size={18} /><span>Text query</span></div>
              <button ref={closeButtonRef} type="button" aria-label="Close text query dialog" onClick={() => setShowTextModal(false)} className="rounded-lg p-1 text-slate-400 hover:text-white"><X size={18} /></button>
            </div>
            <div className="space-y-4 p-6">
              {!canSubmit && <div className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200"><WarningCircle size={18} className="shrink-0" />Backend readiness has not passed. Query submission is disabled.</div>}
              {textError && <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">{textError}</div>}
              <TextInputPanel isLoading={isTextLoading} disabled={!canSubmit} selectedLanguage={voice.selectedLanguage} onLanguageChange={voice.setSelectedLanguage} onSubmit={handleTextSubmit} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
