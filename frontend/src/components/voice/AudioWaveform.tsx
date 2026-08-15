import React from 'react';

interface AudioWaveformProps {
  level: number; // 0.0 to 1.0
  isRecording: boolean;
}

export const AudioWaveform: React.FC<AudioWaveformProps> = ({ level, isRecording }) => {
  // Compute bar heights based on level with small randomness/offsets
  const heightMultiplier = isRecording ? Math.max(0.15, level) : 0.08;

  const bar1 = Math.min(32, Math.max(6, heightMultiplier * 36));
  const bar2 = Math.min(42, Math.max(8, heightMultiplier * 48));
  const bar3 = Math.min(48, Math.max(10, heightMultiplier * 56));
  const bar4 = Math.min(38, Math.max(8, heightMultiplier * 44));
  const bar5 = Math.min(28, Math.max(6, heightMultiplier * 32));

  return (
    <div className="flex items-center justify-center gap-1.5 h-12 py-1" aria-hidden="true">
      <div
        className="w-1 rounded-full bg-accent-primary transition-all duration-75"
        style={{ height: `${bar1}px` }}
      />
      <div
        className="w-1.5 rounded-full bg-accent-primary transition-all duration-75"
        style={{ height: `${bar2}px` }}
      />
      <div
        className="w-1.5 rounded-full bg-accent-primary transition-all duration-75"
        style={{ height: `${bar3}px` }}
      />
      <div
        className="w-1.5 rounded-full bg-accent-primary transition-all duration-75"
        style={{ height: `${bar4}px` }}
      />
      <div
        className="w-1 rounded-full bg-accent-primary transition-all duration-75"
        style={{ height: `${bar5}px` }}
      />
    </div>
  );
};
