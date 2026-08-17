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
import type { ChatTurn } from '../utils/chatSessionHistory';
import {
  clearChatSession,
  loadChatSession,
  saveChatSession,
} from '../utils/chatSessionHistory';
import {
  trackGuardrailRejected,
  trackQueryCompleted,
  trackQuerySubmitted,
} from '../utils/analytics';

export const AskPage: React.FC = () => {
  const [showTextModal, setShowTextModal] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const [textResult, setTextResult] = useState<QueryResponse | null>(null);
  const [isTextLoading, setIsTextLoading] = useState(false);
  const [verifiedPromptCatalog, setVerifiedPromptCatalog] = useState<VerifiedPromptCatalog | null>(null);
  const [verifiedPromptsLoading, setVerifiedPromptsLoading] = useState(true);
  const [verifiedPromptsError, setVerifiedPromptsError] = useState<string | null>(null);
  const [recentQueries, setRecentQueries] = useState(readSessionQueryHistory);
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>(loadChatSession);
  const [lastQuerySource, setLastQuerySource] = useState<'voice' | 'text' | 'sample'>('voice');

  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const verifiedPromptsRequestedRef = useRef(false);
  const trackedRequestIdsRef = useRef<Set<string>>(new Set());
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

  // Sync turn creation to chat history when a new query response arrives
  useEffect(() => {
    if (!activeResult?.transcript.trim()) return;

    // Track query completion and guardrail rejection exactly once per unique request
    if (activeResult.request_id && !trackedRequestIdsRef.current.has(activeResult.request_id)) {
      trackedRequestIdsRef.current.add(activeResult.request_id);

      const isRejected =
        activeResult.guardrail?.decision !== 'ALLOW' ||
        activeResult.state === 'ABSTAINED' ||
        activeResult.state === 'UNSAFE';

      if (isRejected) {
        trackGuardrailRejected({
          reason:
            activeResult.guardrail?.reason ||
            (activeResult.state === 'UNSAFE' ? 'safety_gate' : 'out_of_domain'),
          query_snippet: activeResult.transcript,
        });
      }

      const totalLatency =
        activeResult.timings_ms?.total ?? activeResult.timings_ms?.e2e_total ?? 0;
      trackQueryCompleted({
        total_latency_ms: totalLatency,
        has_citations: Boolean(activeResult.citations && activeResult.citations.length > 0),
        citations_count: activeResult.citations?.length ?? 0,
        groq_synthesis_used: Boolean(activeResult.synthesis),
      });
    }

    // Update session recent queries
    setRecentQueries((current) => {
      const next = prependSessionQuery(current, toSessionQueryHistoryEntry(activeResult));
      writeSessionQueryHistory(next);
      return next;
    });

    // Update chat turns
    setChatTurns((prevTurns) => {
      const existingIndex = prevTurns.findIndex((t) => t.id === activeResult.request_id);
      if (existingIndex >= 0) return prevTurns;

      const newTurn: ChatTurn = {
        id: activeResult.request_id,
        query: activeResult.transcript.trim(),
        language: activeResult.language,
        timestamp: activeResult.completed_at || new Date().toISOString(),
        source: lastQuerySource,
        result: activeResult,
        synthesisLoading: synthesis.isLoading,
        synthesisResult: synthesis.result,
        synthesisError: synthesis.error,
      };

      const updated = [...prevTurns, newTurn];
      saveChatSession(updated);
      return updated;
    });
  }, [activeResult, lastQuerySource, synthesis.isLoading, synthesis.result, synthesis.error]);

  // Sync synthesis updates into active chat turn
  useEffect(() => {
    if (!activeResult?.request_id) return;
    setChatTurns((prevTurns) => {
      const existingIndex = prevTurns.findIndex((t) => t.id === activeResult.request_id);
      if (existingIndex < 0) return prevTurns;

      const target = prevTurns[existingIndex];
      if (
        target.synthesisLoading === synthesis.isLoading &&
        target.synthesisResult === synthesis.result &&
        target.synthesisError === synthesis.error
      ) {
        return prevTurns;
      }

      const updated = [...prevTurns];
      updated[existingIndex] = {
        ...target,
        synthesisLoading: synthesis.isLoading,
        synthesisResult: synthesis.result,
        synthesisError: synthesis.error,
      };
      saveChatSession(updated);
      return updated;
    });
  }, [activeResult, synthesis.isLoading, synthesis.result, synthesis.error]);

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
    sourceType: 'text' | 'sample' = 'text'
  ) => {
    if (!canSubmit) {
      setTextError('The backend is not operationally ready. Open System checks for details.');
      return;
    }

    const targetLanguage = languageOverride ?? toBackendLanguage(voice.selectedLanguage);

    trackQuerySubmitted({
      input_mode: 'text',
      language: targetLanguage,
      source: sourceType === 'sample' ? 'quick_prompt' : 'text_box',
    });

    setLastQuerySource(sourceType);
    setTextResult(null);
    voice.resetToIdle();
    setIsTextLoading(true);
    setTextError(null);
    try {
      const response = await sendTextQuery({
        query: queryText,
        language: targetLanguage,
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

  const handleClearSession = () => {
    setChatTurns([]);
    clearChatSession();
    handleReset();
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
        chatTurns={chatTurns}
        onLanguageChange={voice.setSelectedLanguage}
        onStartRecording={() => {
          setLastQuerySource('voice');
          setTextResult(null);
          setTextError(null);
          voice.startRecording();
        }}
        onStopAndAsk={() => {
          trackQuerySubmitted({
            input_mode: 'voice',
            language: toBackendLanguage(voice.selectedLanguage),
            source: 'mic',
          });
          voice.stopAndAsk();
        }}
        onCancelRecording={voice.cancelRecording}
        onReset={handleReset}
        onClearSession={handleClearSession}
        onToggleTextMode={() => {
          setTextError(null);
          setShowTextModal(true);
        }}
        onOpenDiagnostics={openSystemChecks}
        onSelectVerifiedPrompt={(prompt: string, language: ServerLanguageCode) => {
          setTextError(null);
          setShowTextModal(false);
          void handleTextSubmit(prompt, language, 'sample');
        }}
        onRetryVerifiedPrompts={() => void loadVerifiedPromptCatalog()}
        onClearRecentQueries={() => {
          setRecentQueries([]);
          removeSessionQueryHistory();
        }}
      />

      {showTextModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="text-dialog-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/20 dark:bg-black/30 p-4 backdrop-blur-[2px]"
        >
          <div className="refractive-glass-card refractive-glass-card-primary w-full max-w-2xl overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between border-b border-black/10 dark:border-white/10 p-4">
              <div id="text-dialog-title" className="flex items-center gap-2 text-xs font-bold text-blue-600 dark:text-blue-400">
                <TextT size={18} />
                <span>Text query</span>
              </div>
              <button
                ref={closeButtonRef}
                type="button"
                aria-label="Close text query dialog"
                onClick={() => setShowTextModal(false)}
                className="rounded-lg p-1 text-slate-500 hover:text-black dark:text-slate-400 dark:hover:text-white transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>
            <div className="space-y-4 p-6">
              {!canSubmit && (
                <div className="glass-inner-box flex items-start gap-2 text-xs text-black dark:text-slate-200">
                  <WarningCircle size={18} className="shrink-0 text-amber-600 dark:text-slate-400" />
                  <span className="leading-relaxed text-black dark:text-slate-300">Backend readiness has not passed. Query submission is disabled.</span>
                </div>
              )}
              {textError && (
                <div className="glass-inner-box flex items-start gap-2 text-xs text-rose-800 dark:text-rose-300">
                  <span className="leading-relaxed">{textError}</span>
                </div>
              )}
              <TextInputPanel
                isLoading={isTextLoading}
                disabled={!canSubmit}
                selectedLanguage={voice.selectedLanguage}
                onLanguageChange={voice.setSelectedLanguage}
                onSubmit={(text: string) => {
                  void handleTextSubmit(text, undefined, 'text');
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
