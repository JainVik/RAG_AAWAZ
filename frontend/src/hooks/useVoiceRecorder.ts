import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  LanguageHint,
  PipelineState,
  QueryResponse,
  VoiceClientFrame,
  VoiceErrorState,
  VoiceRecorderState,
} from '../types/api';
import { parseVoiceServerEvent, toBackendLanguage } from '../types/api';
import { getVoiceWebSocketUrl } from '../services/api';
import {
  AUTO_STOP_SILENCE_CONFIG,
  createSilenceDetectionState,
  markRecognizedSpeech,
  observeVolumeForAutoStop,
  startAudioCapture,
  type AudioCaptureHandle,
  type SilenceDetectionState,
} from '../utils/audio';

export interface UseVoiceRecorderReturn {
  state: VoiceRecorderState;
  audioLevel: number;
  recordingDuration: number;
  partialTranscript: string;
  detectedLanguage: string | null;
  pipelineState: PipelineState | null;
  result: QueryResponse | null;
  error: VoiceErrorState | null;
  selectedLanguage: LanguageHint;
  setSelectedLanguage: (language: LanguageHint) => void;
  startRecording: () => Promise<void>;
  stopAndAsk: () => void;
  cancelRecording: () => void;
  resetToIdle: () => void;
  isBackendConnected: boolean;
}

const MAX_RECORDING_SECONDS = 60;
const MAX_QUEUED_CHUNKS = 100;

export function useVoiceRecorder(): UseVoiceRecorderReturn {
  const [state, setState] = useState<VoiceRecorderState>('idle');
  const [audioLevel, setAudioLevel] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [partialTranscript, setPartialTranscript] = useState('');
  const [detectedLanguage, setDetectedLanguage] = useState<string | null>(null);
  const [pipelineState, setPipelineState] = useState<PipelineState | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<VoiceErrorState | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<LanguageHint>('auto');
  const [isBackendConnected, setIsBackendConnected] = useState(false);

  const stateRef = useRef<VoiceRecorderState>('idle');
  const socketRef = useRef<WebSocket | null>(null);
  const captureRef = useRef<AudioCaptureHandle | null>(null);
  const timerRef = useRef<number | null>(null);
  const sequenceRef = useRef(0);
  const chunkCountRef = useRef(0);
  const queuedChunksRef = useRef<string[]>([]);
  const pendingEndRef = useRef(false);
  const intentionalCloseRef = useRef(false);
  const sessionRef = useRef(0);
  const recordingStartedRef = useRef(0);
  const finishRef = useRef<() => void>(() => undefined);
  const silenceStateRef = useRef<SilenceDetectionState>(createSilenceDetectionState(0));
  const autoStopTriggeredRef = useRef(false);
  const lastPartialTextRef = useRef('');
  const lastPartialChangeAtRef = useRef<number | null>(null);
  const latestVolumeRef = useRef(0);
  const peakVolumeRef = useRef(0);

  const transition = useCallback((next: VoiceRecorderState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  const stopCapture = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    captureRef.current?.stop();
    captureRef.current = null;
    setAudioLevel(0);
  }, []);

  const closeSocket = useCallback(() => {
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket && socket.readyState !== WebSocket.CLOSED) {
      intentionalCloseRef.current = true;
      socket.close(1000, 'Client session complete');
    }
    setIsBackendConnected(false);
  }, []);

  const cleanup = useCallback(() => {
    stopCapture();
    closeSocket();
    queuedChunksRef.current = [];
    pendingEndRef.current = false;
    autoStopTriggeredRef.current = false;
    silenceStateRef.current = createSilenceDetectionState(0);
    lastPartialTextRef.current = '';
    lastPartialChangeAtRef.current = null;
    latestVolumeRef.current = 0;
    peakVolumeRef.current = 0;
  }, [closeSocket, stopCapture]);

  const sendFrame = useCallback((frame: VoiceClientFrame): boolean => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(frame));
    return true;
  }, []);

  const failSession = useCallback(
    (nextError: VoiceErrorState) => {
      cleanup();
      setError(nextError);
      setPipelineState(nextError.state || 'FAILED');
      transition('terminal');
    },
    [cleanup, transition]
  );

  const finishRecording = useCallback(() => {
    if (stateRef.current !== 'recording') return;
    const elapsedMs = Date.now() - recordingStartedRef.current;
    if (chunkCountRef.current < 3 && elapsedMs < 1_000) {
      failSession({
        type: 'too_short',
        code: 'VALIDATION_ERROR',
        state: 'NEEDS_REPEAT',
        message: 'Audio was too short. Please speak your complete question and try again.',
        retryable: true,
      });
      return;
    }
    stopCapture();
    transition('processing');
    setPipelineState('STT_FINAL');
    if (!sendFrame({ type: 'end_of_stream', version: '1' })) {
      pendingEndRef.current = true;
    }
  }, [failSession, sendFrame, stopCapture, transition]);

  finishRef.current = finishRecording;

  const startRecording = useCallback(async () => {
    cleanup();
    sessionRef.current += 1;
    const session = sessionRef.current;
    intentionalCloseRef.current = false;
    sequenceRef.current = 0;
    chunkCountRef.current = 0;
    queuedChunksRef.current = [];
    pendingEndRef.current = false;
    setError(null);
    setResult(null);
    setPartialTranscript('');
    setDetectedLanguage(null);
    setPipelineState(null);
    setRecordingDuration(0);
    transition('requesting_permission');

    try {
      const capture = await startAudioCapture((base64Chunk, volume) => {
        if (sessionRef.current !== session || stateRef.current === 'terminal') return;
        setAudioLevel(volume);
        latestVolumeRef.current = volume;
        peakVolumeRef.current = Math.max(peakVolumeRef.current, volume);
        chunkCountRef.current += 1;
        if (stateRef.current === 'recording' && !autoStopTriggeredRef.current) {
          const observation = observeVolumeForAutoStop(
            silenceStateRef.current,
            volume,
            Date.now()
          );
          silenceStateRef.current = observation.state;
          if (observation.shouldStop) {
            autoStopTriggeredRef.current = true;
            finishRef.current();
            return;
          }
        }
        const frame = {
          type: 'audio_chunk' as const,
          version: '1' as const,
          sequence: sequenceRef.current,
          audio_b64: base64Chunk,
        };
        if (sendFrame(frame)) {
          sequenceRef.current += 1;
          return;
        }
        if (queuedChunksRef.current.length >= MAX_QUEUED_CHUNKS) {
          failSession({
            type: 'socket_timeout',
            code: 'DEPENDENCY_UNAVAILABLE',
            state: 'DEPENDENCY_UNAVAILABLE',
            message: 'The voice connection did not become ready in time.',
            retryable: true,
          });
          return;
        }
        queuedChunksRef.current.push(base64Chunk);
      });
      if (sessionRef.current !== session) {
        capture.stop();
        return;
      }
      captureRef.current = capture;
      recordingStartedRef.current = Date.now();
      silenceStateRef.current = createSilenceDetectionState(recordingStartedRef.current);
      transition('recording');
      setPipelineState('AUDIO_RECEIVED');

      const socket = new WebSocket(getVoiceWebSocketUrl());
      socketRef.current = socket;
      socket.onopen = () => {
        if (sessionRef.current !== session) return;
        setIsBackendConnected(true);
        sendFrame({
          type: 'start',
          version: '1',
          request_id: crypto.randomUUID(),
          encoding: 'pcm_s16le',
          sample_rate_hz: 16000,
          language: toBackendLanguage(selectedLanguage),
        });
        for (const audio_b64 of queuedChunksRef.current) {
          sendFrame({
            type: 'audio_chunk',
            version: '1',
            sequence: sequenceRef.current++,
            audio_b64,
          });
        }
        queuedChunksRef.current = [];
        if (pendingEndRef.current) {
          pendingEndRef.current = false;
          sendFrame({ type: 'end_of_stream', version: '1' });
        }
      };
      socket.onmessage = (message) => {
        if (sessionRef.current !== session) return;
        try {
          const event = parseVoiceServerEvent(JSON.parse(String(message.data)) as unknown);
          if (event.type === 'stt_partial') {
            setPartialTranscript(event.payload.text);
            setDetectedLanguage(event.payload.language);
            const normalizedPartial = event.payload.text.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
            if (
              normalizedPartial &&
              normalizedPartial !== lastPartialTextRef.current &&
              stateRef.current === 'recording'
            ) {
              lastPartialTextRef.current = normalizedPartial;
              lastPartialChangeAtRef.current = Date.now();
              silenceStateRef.current = markRecognizedSpeech(
                silenceStateRef.current,
                Date.now()
              );
            }
          } else if (event.type === 'pipeline_state') {
            setPipelineState(event.payload.state);
          } else if (event.type === 'answer') {
            stopCapture();
            closeSocket();
            setResult(event.payload);
            setPartialTranscript(event.payload.transcript);
            setDetectedLanguage(event.payload.language);
            setPipelineState(event.payload.state);
            transition('terminal');
          } else {
            failSession({
              type: 'backend_error',
              code: event.payload.code,
              state: event.payload.state,
              message: event.payload.message,
              retryable: event.payload.retryable,
              details: event.payload.details,
              timingsMs: event.payload.timings_ms,
            });
          }
        } catch (eventError) {
          failSession({
            type: 'protocol_error',
            code: 'VALIDATION_ERROR',
            state: 'FAILED',
            message:
              eventError instanceof Error
                ? eventError.message
                : 'The backend returned an invalid voice event.',
            retryable: false,
          });
        }
      };
      socket.onerror = () => {
        if (sessionRef.current !== session || intentionalCloseRef.current) return;
        failSession({
          type: 'socket_error',
          code: 'DEPENDENCY_UNAVAILABLE',
          state: 'DEPENDENCY_UNAVAILABLE',
          message: 'The backend voice streaming service is unreachable.',
          retryable: true,
        });
      };
      socket.onclose = (event) => {
        setIsBackendConnected(false);
        if (
          sessionRef.current === session &&
          !intentionalCloseRef.current &&
          stateRef.current !== 'terminal'
        ) {
          failSession({
            type: 'socket_error',
            code: 'DEPENDENCY_UNAVAILABLE',
            state: 'DEPENDENCY_UNAVAILABLE',
            message: event.reason || 'The voice connection closed before a terminal response.',
            retryable: true,
          });
        }
      };

      timerRef.current = window.setInterval(() => {
        const now = Date.now();
        const elapsedMs = now - recordingStartedRef.current;
        const elapsed = Math.floor(elapsedMs / 1000);
        setRecordingDuration(elapsed);
        const adaptiveQuietThreshold = Math.max(
          AUTO_STOP_SILENCE_CONFIG.speechVolumeThreshold,
          peakVolumeRef.current * 0.35
        );
        const transcriptStableForSilenceWindow =
          lastPartialChangeAtRef.current !== null &&
          now - lastPartialChangeAtRef.current >= AUTO_STOP_SILENCE_CONFIG.silenceMs;
        const microphoneIsQuiet = latestVolumeRef.current < adaptiveQuietThreshold;
        if (
          stateRef.current === 'recording' &&
          !autoStopTriggeredRef.current &&
          elapsedMs >= AUTO_STOP_SILENCE_CONFIG.minimumRecordingMs &&
          transcriptStableForSilenceWindow &&
          microphoneIsQuiet
        ) {
          autoStopTriggeredRef.current = true;
          finishRef.current();
          return;
        }
        if (elapsed >= MAX_RECORDING_SECONDS) finishRef.current();
      }, 250);
    } catch (captureError) {
      cleanup();
      transition('idle');
      const permissionDenied =
        captureError instanceof DOMException && captureError.name === 'NotAllowedError';
      const noMicrophone = captureError instanceof DOMException && captureError.name === 'NotFoundError';
      setError({
        type: permissionDenied ? 'permission_denied' : noMicrophone ? 'no_microphone' : 'unsupported',
        message: permissionDenied
          ? 'Microphone permission was denied. Allow access or use Text mode.'
          : noMicrophone
            ? 'No microphone was detected. Connect one or use Text mode.'
            : 'This browser could not start compatible microphone capture. Use Text mode.',
        retryable: permissionDenied,
      });
    }
  }, [cleanup, closeSocket, failSession, selectedLanguage, sendFrame, stopCapture, transition]);

  const cancelRecording = useCallback(() => {
    sessionRef.current += 1;
    cleanup();
    setError(null);
    setPartialTranscript('');
    setPipelineState(null);
    transition('idle');
  }, [cleanup, transition]);

  const resetToIdle = useCallback(() => {
    sessionRef.current += 1;
    cleanup();
    setError(null);
    setResult(null);
    setPartialTranscript('');
    setDetectedLanguage(null);
    setPipelineState(null);
    setRecordingDuration(0);
    transition('idle');
  }, [cleanup, transition]);

  useEffect(() => {
    const stopOnPageHide = () => {
      sessionRef.current += 1;
      cleanup();
    };
    window.addEventListener('pagehide', stopOnPageHide);
    return () => {
      window.removeEventListener('pagehide', stopOnPageHide);
      stopOnPageHide();
    };
  }, [cleanup]);

  return {
    state,
    audioLevel,
    recordingDuration,
    partialTranscript,
    detectedLanguage,
    pipelineState,
    result,
    error,
    selectedLanguage,
    setSelectedLanguage,
    startRecording,
    stopAndAsk: finishRecording,
    cancelRecording,
    resetToIdle,
    isBackendConnected,
  };
}
