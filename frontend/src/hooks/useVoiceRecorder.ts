import { useState, useRef, useCallback, useEffect } from 'react';
import { startAudioCapture } from '../utils/audio';
import type {
  VoiceRecorderState,
  VoiceRecorderError,
  VoiceResultData,
  VoiceServerEvent,
  PipelineState,
  Language,
} from '../types/api';

export interface UseVoiceRecorderReturn {
  state: VoiceRecorderState;
  audioLevel: number;
  recordingDuration: number;
  partialTranscript: string;
  detectedLanguage: string | null;
  pipelineState: PipelineState | null;
  result: VoiceResultData | null;
  error: VoiceRecorderError | null;
  selectedLanguage: Language;
  setSelectedLanguage: (lang: Language) => void;
  startRecording: () => Promise<void>;
  stopAndAsk: () => void;
  cancelRecording: () => void;
  resetToIdle: () => void;
  isBackendConnected: boolean;
}

export function useVoiceRecorder(): UseVoiceRecorderReturn {
  const [state, setState] = useState<VoiceRecorderState>('idle');
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [recordingDuration, setRecordingDuration] = useState<number>(0);
  const [partialTranscript, setPartialTranscript] = useState<string>('');
  const [detectedLanguage, setDetectedLanguage] = useState<string | null>(null);
  const [pipelineState, setPipelineState] = useState<PipelineState | null>(null);
  const [result, setResult] = useState<VoiceResultData | null>(null);
  const [error, setError] = useState<VoiceRecorderError | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState<Language>('auto' as Language);
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(false);

  // References
  const socketRef = useRef<WebSocket | null>(null);
  const captureHandleRef = useRef<{ stop: () => void } | null>(null);
  const timerRef = useRef<number | null>(null);
  const sequenceRef = useRef<number>(0);
  const audioChunksCountRef = useRef<number>(0);

  // Cleanup all audio and socket resources
  const cleanupAudioAndSocket = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (captureHandleRef.current) {
      try {
        captureHandleRef.current.stop();
      } catch {
        // Ignore audio stop errors
      }
      captureHandleRef.current = null;
    }
    if (socketRef.current) {
      try {
        if (socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.close(1000, 'Session completed or reset');
        }
      } catch {
        // Ignore socket close errors
      }
      socketRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      cleanupAudioAndSocket();
    };
  }, [cleanupAudioAndSocket]);

  /**
   * Helper to send typed JSON frames over WebSocket
   */
  const sendFrame = useCallback((frame: Record<string, unknown>) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      try {
        socketRef.current.send(JSON.stringify(frame));
      } catch (err) {
        console.error('Failed to send WebSocket frame:', err);
      }
    }
  }, []);

  /**
   * Handle incoming server events from real FastAPI WebSocket
   */
  const handleServerEvent = useCallback(
    (event: VoiceServerEvent) => {
      switch (event.type) {
        case 'stt_partial': {
          const text = event.transcript || event.payload?.text;
          const lang = event.language || event.payload?.language;
          if (text) {
            setPartialTranscript(text);
          }
          if (lang) {
            setDetectedLanguage(lang);
          }
          break;
        }

        case 'pipeline_state': {
          const pState = event.state || event.payload?.state;
          if (pState) {
            setPipelineState(pState);
          }
          break;
        }

        case 'answer': {
          cleanupAudioAndSocket();
          setState('terminal');
          setPipelineState('COMPLETED');
          setIsBackendConnected(true);

          const answerPayload = event.payload;
          setResult({
            request_id: event.request_id || answerPayload?.request_id || `req_${Date.now()}`,
            state: 'COMPLETED',
            answer_mode: answerPayload?.answer_mode || event.answer_mode || 'grounded_extractive',
            transcript: answerPayload?.transcript || event.transcript || partialTranscript || '',
            language: answerPayload?.language || event.language || detectedLanguage || 'hi',
            answer_text: answerPayload?.answer_text || answerPayload?.answer || event.answer_text || null,
            abstention_reason: answerPayload?.abstention_reason || event.abstention_reason || null,
            guardrail: answerPayload?.guardrail || event.guardrail,
            citations: answerPayload?.citations || event.citations || [],
            timings: answerPayload?.timings || event.timings || {
              audio_received_ms: 0,
              stt_final_ms: 0,
              retrieval_ms: 0,
              answer_ms: 0,
              total_ms: 0,
            },
          });
          break;
        }

        case 'error': {
          cleanupAudioAndSocket();
          setState('terminal');
          setPipelineState('FAILED');
          const errorMsg = event.message || event.payload?.message || 'The server encountered an error processing your query.';
          setError({
            type: 'backend_error',
            message: errorMsg,
            details: event.details || event.payload?.details,
            retryable: event.retryable ?? true,
          });
          break;
        }
      }
    },
    [cleanupAudioAndSocket, partialTranscript, detectedLanguage]
  );

  /**
   * Start microphone capture and connect real WebSocket
   */
  const startRecording = useCallback(async () => {
    cleanupAudioAndSocket();
    setError(null);
    setResult(null);
    setPartialTranscript('');
    setPipelineState(null);
    setRecordingDuration(0);
    sequenceRef.current = 0;
    audioChunksCountRef.current = 0;

    const requestId = `req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

    setState('requesting_permission');

    try {
      // Connect WebSocket to real backend
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${window.location.host}/v1/query/voice`;

      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        setIsBackendConnected(true);
        sendFrame({
          type: 'start',
          version: '1',
          request_id: requestId,
          encoding: 'pcm_s16le',
          sample_rate_hz: 16000,
          language: selectedLanguage,
        });
      };

      socket.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as VoiceServerEvent;
          handleServerEvent(data);
        } catch {
          // Malformed event
        }
      };

      socket.onerror = () => {
        setIsBackendConnected(false);
        cleanupAudioAndSocket();
        setState('terminal');
        setError({
          type: 'socket_error',
          message: 'Backend voice streaming service is unreachable at 127.0.0.1:8000. Please start the backend service (make dev).',
          retryable: true,
        });
      };

      socket.onclose = (event) => {
        setIsBackendConnected(false);
        // If closed prematurely while still recording/processing without result
        if (state === 'recording' || state === 'processing') {
          cleanupAudioAndSocket();
          setState('terminal');
          setError({
            type: 'socket_error',
            message: event.reason || 'Voice streaming connection was closed by the backend.',
            retryable: true,
          });
        }
      };

      // Start capturing 16kHz PCM audio
      const captureHandle = await startAudioCapture((base64Chunk, volume) => {
        setAudioLevel(volume);
        audioChunksCountRef.current += 1;

        if (socket && socket.readyState === WebSocket.OPEN) {
          sendFrame({
            type: 'audio_chunk',
            version: '1',
            sequence: sequenceRef.current++,
            audio_b64: base64Chunk,
          });
        }
      });

      captureHandleRef.current = captureHandle;
      setState('recording');
      setPipelineState('AUDIO_RECEIVED');

      // Start duration timer
      const startTime = Date.now();
      timerRef.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        setRecordingDuration(elapsed);

        // Auto-stop at 60 seconds
        if (elapsed >= 60) {
          stopAndAsk();
        }
      }, 250);
    } catch (err: unknown) {
      cleanupAudioAndSocket();
      setState('idle');
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        setError({
          type: 'permission_denied',
          message: 'Microphone permission was denied. Please allow microphone access in browser settings or use Text mode.',
          retryable: true,
        });
      } else if (err instanceof DOMException && err.name === 'NotFoundError') {
        setError({
          type: 'no_microphone',
          message: 'No microphone was detected. Please connect a microphone or use Text mode.',
          retryable: false,
        });
      } else {
        setError({
          type: 'unsupported',
          message: 'Web Audio recording is not supported in this browser. Please switch to Text mode.',
          retryable: false,
        });
      }
    }
  }, [selectedLanguage, handleServerEvent, cleanupAudioAndSocket, sendFrame, state]);

  /**
   * Stop recording and request final answer from backend
   */
  const stopAndAsk = useCallback(() => {
    if (state !== 'recording') return;

    // Check for too short audio (< 0.5s or < 3 chunks)
    if (audioChunksCountRef.current < 3 && recordingDuration < 1) {
      cleanupAudioAndSocket();
      setState('terminal');
      setPipelineState('NEEDS_REPEAT');
      setError({
        type: 'too_short',
        message: 'Audio was too short to transcribe. Please hold the button and speak your full question.',
        retryable: true,
      });
      return;
    }

    setState('processing');
    setPipelineState('STT_PARTIAL');

    // Send end_of_stream frame to backend
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      sendFrame({
        type: 'end_of_stream',
        version: '1',
      });
    } else {
      // Socket not open — report real connection failure
      cleanupAudioAndSocket();
      setState('terminal');
      setError({
        type: 'socket_error',
        message: 'Backend voice streaming connection is offline. Please start the backend service.',
        retryable: true,
      });
    }
  }, [state, recordingDuration, cleanupAudioAndSocket, sendFrame]);

  /**
   * Cancel the current recording session
   */
  const cancelRecording = useCallback(() => {
    cleanupAudioAndSocket();
    setState('idle');
    setPipelineState(null);
    setPartialTranscript('');
    setError(null);
  }, [cleanupAudioAndSocket]);

  /**
   * Reset session back to idle
   */
  const resetToIdle = useCallback(() => {
    cleanupAudioAndSocket();
    setState('idle');
    setResult(null);
    setError(null);
    setPartialTranscript('');
    setDetectedLanguage(null);
    setPipelineState(null);
    setRecordingDuration(0);
  }, [cleanupAudioAndSocket]);

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
    stopAndAsk,
    cancelRecording,
    resetToIdle,
    isBackendConnected,
  };
}
