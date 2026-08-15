import React from 'react';
import type { VoiceState } from '../../types/api';

interface VoiceOrbProps {
  state: VoiceState;
  audioLevel: number; // 0.0 to 1.0
  onClick?: () => void;
  disabled?: boolean;
}

export const VoiceOrb: React.FC<VoiceOrbProps> = ({ state, audioLevel, onClick, disabled = false }) => {
  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';
  const isRequesting = state === 'requesting_permission';

  // Dynamic scale calculation based on mic audio volume
  const scale = isRecording ? 1 + Math.min(0.2, audioLevel * 0.3) : isProcessing ? 1.04 : 1;
  const glowOpacity = isRecording ? 0.7 + Math.min(0.3, audioLevel * 0.4) : isProcessing ? 0.6 : 0.4;

  // Determine dynamic letter text according to current state
  const getDisplayText = () => {
    if (isRecording) return 'Listening';
    if (isProcessing) return 'Generating';
    if (isRequesting) return 'Connecting';
    return 'VANI RAG';
  };

  const displayText = getDisplayText();
  const letters = displayText.split('');

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="relative flex items-center justify-center w-64 h-64 sm:w-72 sm:h-72 cursor-pointer select-none group disabled:cursor-not-allowed disabled:opacity-55"
      aria-label={isRecording ? 'Listening. Click to stop and ask.' : 'Click to start voice recording'}
    >
      {/* Outer ambient diffuse glow responding to audioLevel */}
      <div
        className="absolute inset-0 rounded-full blur-3xl transition-all duration-300 pointer-events-none"
        style={{
          background: isRecording
            ? 'radial-gradient(circle, rgba(6, 182, 212, 0.45) 0%, rgba(173, 95, 255, 0.35) 45%, transparent 70%)'
            : isProcessing
            ? 'radial-gradient(circle, rgba(214, 10, 71, 0.4) 0%, rgba(71, 30, 236, 0.35) 45%, transparent 70%)'
            : 'radial-gradient(circle, rgba(71, 30, 236, 0.35) 0%, rgba(173, 95, 255, 0.2) 50%, transparent 70%)',
          opacity: glowOpacity,
          transform: `scale(${scale * 1.25})`,
        }}
      />

      {/* Main Orb Loader Wrapper */}
      <div
        className={`orb-loader-wrapper group-hover:scale-105 transition-transform duration-200 ${
          isRecording ? 'orb-loader-recording' : isProcessing ? 'orb-loader-processing' : ''
        }`}
        style={{
          transform: `scale(${scale})`,
        }}
      >
        {/* Dynamic Animated Letters */}
        {letters.map((char, idx) => (
          <span
            key={`${displayText}-${idx}`}
            className="orb-loader-letter"
            style={{
              animationDelay: `${idx * 0.1}s`,
              marginRight: char === ' ' ? '0.35rem' : '0.04rem',
            }}
          >
            {char === ' ' ? '\u00A0' : char}
          </span>
        ))}

        {/* The Rotating Inset-Shadow Ball Element */}
        <div
          className={`orb-loader ${
            isRecording ? 'orb-loader-recording' : isProcessing ? 'orb-loader-processing' : ''
          }`}
        />
      </div>

      {/* Subtle pulse ring when recording */}
      {isRecording && (
        <div className="absolute inset-4 rounded-full border border-cyan-400/40 animate-ping pointer-events-none opacity-30" />
      )}
    </button>
  );
};
