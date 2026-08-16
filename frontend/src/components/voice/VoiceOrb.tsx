import React from 'react';
import type { VoiceState } from '../../types/api';

interface VoiceOrbProps {
  state: VoiceState;
  audioLevel: number; // 0.0 to 1.0
  onClick?: () => void;
  disabled?: boolean;
  size?: 'lg' | 'sm';
}

export const VoiceOrb: React.FC<VoiceOrbProps> = ({
  state,
  audioLevel,
  onClick,
  disabled = false,
  size = 'lg',
}) => {
  const isRecording = state === 'recording';
  const isProcessing = state === 'processing';
  const isRequesting = state === 'requesting_permission';

  // Dynamic scale calculation based on mic audio volume
  const scale = isRecording ? 1 + Math.min(0.2, audioLevel * 0.3) : isProcessing ? 1.04 : 1;
  const glowOpacity = isRecording ? 0.7 + Math.min(0.3, audioLevel * 0.4) : isProcessing ? 0.6 : 0.4;

  const getDisplayText = () => {
    if (isRecording) return 'Listening';
    if (isProcessing) return 'Generating';
    if (isRequesting) return 'Connecting';
    return 'VANI RAG';
  };

  const displayText = getDisplayText();
  const letters = displayText.split('');

  if (size === 'sm') {
    const smScale = 42 / 180; // Scale 180px down to ~42px
    return (
      <div
        className="relative flex items-center justify-center w-11 h-11 shrink-0 select-none"
        aria-label="Animated VANI Voice Orb"
      >
        {/* Outer ambient diffuse glow responding to audioLevel */}
        <div
          className="absolute inset-0 rounded-full blur-md transition-all duration-300 pointer-events-none"
          style={{
            background: isRecording
              ? 'radial-gradient(circle, rgba(6, 182, 212, 0.7) 0%, rgba(173, 95, 255, 0.5) 45%, transparent 70%)'
              : isProcessing
              ? 'radial-gradient(circle, rgba(214, 10, 71, 0.6) 0%, rgba(71, 30, 236, 0.5) 45%, transparent 70%)'
              : 'radial-gradient(circle, rgba(71, 30, 236, 0.6) 0%, rgba(173, 95, 255, 0.4) 50%, transparent 70%)',
            opacity: glowOpacity,
            transform: `scale(${scale * 1.3})`,
          }}
        />

        {/* Exact same Uiverse Loader Wrapper scaled down */}
        <div
          className="loader-wrapper"
          style={{
            transform: `scale(${smScale * scale})`,
            transformOrigin: 'center center',
          }}
        >
          {/* Dynamic Animated Letters */}
          {letters.map((char: string, idx: number) => (
            <span
              key={`${displayText}-${idx}`}
              className="loader-letter text-sm font-semibold"
              style={{
                animationDelay: `${idx * 0.1}s`,
                marginRight: char === ' ' ? '0.35rem' : '0.02rem',
              }}
            >
              {char === ' ' ? '\u00A0' : char}
            </span>
          ))}

          {/* The Exact Rotating Inset-Shadow Ball Element */}
          <div className="loader" />
        </div>

        {/* Subtle pulse ring when recording */}
        {isRecording && (
          <div className="absolute -inset-1 rounded-full border border-cyan-400/50 animate-ping pointer-events-none opacity-40" />
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="relative flex items-center justify-center w-64 h-64 sm:w-72 sm:h-72 cursor-pointer select-none group disabled:cursor-not-allowed"
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

      {/* Main Uiverse Loader Wrapper */}
      <div
        className="loader-wrapper group-hover:scale-105 transition-transform duration-200"
        style={{
          transform: `scale(${scale})`,
        }}
      >
        {/* Dynamic Animated Letters */}
        {letters.map((char: string, idx: number) => (
          <span
            key={`${displayText}-${idx}`}
            className="loader-letter"
            style={{
              animationDelay: `${idx * 0.1}s`,
              marginRight: char === ' ' ? '0.35rem' : '0.02rem',
            }}
          >
            {char === ' ' ? '\u00A0' : char}
          </span>
        ))}

        {/* The Rotating Inset-Shadow Ball Element */}
        <div className="loader" />
      </div>

      {/* Subtle pulse ring when recording */}
      {isRecording && (
        <div className="absolute inset-4 rounded-full border border-cyan-400/40 animate-ping pointer-events-none opacity-30" />
      )}
    </button>
  );
};
