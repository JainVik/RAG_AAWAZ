/**
 * Audio capture and conversion utilities for 16 kHz signed 16-bit PCM streaming.
 */

export interface AudioCaptureHandle {
  stream: MediaStream;
  audioContext: AudioContext;
  processor: ScriptProcessorNode | AudioWorkletNode;
  source: MediaStreamAudioSourceNode;
  stop: () => void;
}

export interface SilenceDetectionState {
  startedAtMs: number;
  lastSpeechAtMs: number | null;
  consecutiveSpeechChunks: number;
  speechDetected: boolean;
}

export interface SilenceDetectionConfig {
  silenceMs: number;
  minimumRecordingMs: number;
  speechVolumeThreshold: number;
  speechConfirmationChunks: number;
}

export const AUTO_STOP_SILENCE_CONFIG: SilenceDetectionConfig = {
  silenceMs: 1_500,
  minimumRecordingMs: 1_200,
  speechVolumeThreshold: 0.06,
  speechConfirmationChunks: 2,
};

export function createSilenceDetectionState(startedAtMs: number): SilenceDetectionState {
  return {
    startedAtMs,
    lastSpeechAtMs: null,
    consecutiveSpeechChunks: 0,
    speechDetected: false,
  };
}

export function markRecognizedSpeech(
  state: SilenceDetectionState,
  nowMs: number
): SilenceDetectionState {
  return { ...state, speechDetected: true, lastSpeechAtMs: nowMs };
}

export function observeVolumeForAutoStop(
  state: SilenceDetectionState,
  volume: number,
  nowMs: number,
  config: SilenceDetectionConfig = AUTO_STOP_SILENCE_CONFIG
): { state: SilenceDetectionState; shouldStop: boolean } {
  const isSpeechVolume = volume >= config.speechVolumeThreshold;
  const consecutiveSpeechChunks = isSpeechVolume
    ? state.consecutiveSpeechChunks + 1
    : 0;
  const speechDetected =
    state.speechDetected || consecutiveSpeechChunks >= config.speechConfirmationChunks;
  const lastSpeechAtMs = isSpeechVolume && speechDetected
    ? nowMs
    : state.lastSpeechAtMs;
  const nextState = {
    ...state,
    consecutiveSpeechChunks,
    speechDetected,
    lastSpeechAtMs,
  };
  const recordingLongEnough = nowMs - state.startedAtMs >= config.minimumRecordingMs;
  const silentLongEnough =
    lastSpeechAtMs !== null && nowMs - lastSpeechAtMs >= config.silenceMs;
  return {
    state: nextState,
    shouldStop: speechDetected && recordingLongEnough && silentLongEnough,
  };
}

/**
 * Convert Float32Array audio samples (native sample rate) to 16kHz signed 16-bit little-endian PCM base64
 */
export function resampleAndEncodePCM16(
  inputBuffer: Float32Array,
  inputSampleRate: number,
  targetSampleRate = 16000
): { base64: string; volume: number } {
  const compressionRatio = inputSampleRate / targetSampleRate;
  const targetLength = Math.round(inputBuffer.length / compressionRatio);
  const pcm16 = new Int16Array(targetLength);

  let sumSquares = 0;

  for (let i = 0; i < targetLength; i++) {
    const originalIndex = Math.floor(i * compressionRatio);
    // Clamp sample between -1.0 and 1.0
    const sample = Math.max(-1, Math.min(1, inputBuffer[originalIndex]));
    sumSquares += sample * sample;
    // Convert to signed 16-bit PCM (-32768 to 32767)
    pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }

  // Calculate RMS volume level (0.0 to 1.0)
  const rms = Math.sqrt(sumSquares / (inputBuffer.length || 1));
  const volume = Math.min(1, rms * 4); // Boost visually

  // Convert to Base64
  const bytes = new Uint8Array(pcm16.buffer);
  let binary = '';
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const base64 = btoa(binary);

  return { base64, volume };
}

/**
 * Start capturing microphone stream and deliver resampled PCM chunks via callback
 */
export async function startAudioCapture(
  onChunk: (base64Chunk: string, volume: number) => void
): Promise<AudioCaptureHandle> {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('UNSUPPORTED_BROWSER_AUDIO');
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    video: false,
  });

  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const audioContext = new AudioCtx();

  const source = audioContext.createMediaStreamSource(stream);
  // Buffer size 4096 gives ~85ms chunks at 48kHz, suitable for low latency streaming
  const processor = audioContext.createScriptProcessor(4096, 1, 1);

  processor.onaudioprocess = (e) => {
    const inputData = e.inputBuffer.getChannelData(0);
    const { base64, volume } = resampleAndEncodePCM16(
      inputData,
      audioContext.sampleRate,
      16000
    );
    if (base64) {
      onChunk(base64, volume);
    }
  };

  source.connect(processor);
  processor.connect(audioContext.destination);

  const stop = () => {
    try {
      processor.disconnect();
      source.disconnect();
      if (audioContext.state !== 'closed') {
        audioContext.close();
      }
    } catch {
      // Ignore disconnect errors during teardown
    }
    // Stop all media tracks
    stream.getTracks().forEach((track) => {
      track.stop();
    });
  };

  return {
    stream,
    audioContext,
    processor,
    source,
    stop,
  };
}
