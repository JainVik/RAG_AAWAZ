import { CheckCircle, ChatCenteredText, Info } from '@phosphor-icons/react';
import { getLanguageDisplayLabel } from '../../types/api';

interface LiveTranscriptCardProps {
  transcript: string;
  isPartial: boolean;
  detectedLanguage: string;
  confidence: number | null;
  onSelectSamplePrompt?: (prompt: string) => void;
}

export const LiveTranscriptCard: React.FC<LiveTranscriptCardProps> = ({
  transcript,
  isPartial,
  detectedLanguage,
  confidence,
  onSelectSamplePrompt,
}) => {
  const samplePrompts = [
    { text: 'गोवा सरकारची जलसंधारण योजना काय आहे?', lang: 'मराठी' },
    { text: 'मुख्यमंत्री रोजगार योजना के लिए क्या पात्रता है?', lang: 'हिंदी' },
    { text: 'What is the procedure for obtaining a revenue certificate in Goa?', lang: 'English' },
  ];

  if (!transcript) {
    return (
      <div className="p-6 bg-surface-subtle/70 border border-subtle rounded-2xl space-y-4">
        <div className="flex items-center gap-2 text-xs font-bold text-secondary uppercase tracking-wider">
          <ChatCenteredText size={16} className="text-accent-primary" />
          <span>Sample Questions from Goa Governance Corpus</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          {samplePrompts.map((p, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectSamplePrompt?.(p.text)}
              className="p-3 bg-surface hover:bg-accent-subtle/30 border border-subtle hover:border-accent-border rounded-xl text-left transition-all cursor-pointer group"
            >
              <span className="text-[10px] font-semibold font-mono text-accent-primary block mb-1">
                {p.lang}
              </span>
              <p className="text-xs text-primary group-hover:text-accent-primary leading-relaxed font-medium">
                {p.text}
              </p>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      aria-live="polite"
      className="p-5 sm:p-6 bg-surface border border-subtle rounded-2xl shadow-xs space-y-3 transition-all"
    >
      {/* Header with transcript status & detected language */}
      <div className="flex items-center justify-between gap-2 border-b border-subtle pb-3">
        <div className="flex items-center gap-2">
          {isPartial ? (
            <div className="flex items-center gap-2 text-xs font-bold text-accent-primary">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-primary opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent-primary" />
              </span>
              <span>Live Speech Transcript (Revisable Stream)</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-400">
              <CheckCircle size={16} weight="fill" />
              <span>Final Question Transcript</span>
            </div>
          )}
        </div>

        {/* Language & Confidence Metadata */}
        <div className="flex items-center gap-2">
          {detectedLanguage && detectedLanguage !== 'unknown' && (
            <span className="px-2 py-0.5 rounded bg-surface-subtle border border-subtle text-[10px] font-mono font-bold text-primary uppercase">
              {getLanguageDisplayLabel(detectedLanguage)}
            </span>
          )}

          <div
            className="hidden sm:inline-flex items-center gap-1 text-[11px] text-muted"
            title="Sarvam realtime events do not provide recognition confidence. Never fabricated."
          >
            <Info size={13} />
            <span>
              {confidence !== null
                ? `Confidence: ${(confidence * 100).toFixed(1)}%`
                : 'Recognition confidence unavailable'}
            </span>
          </div>
        </div>
      </div>

      {/* Transcript Text Body */}
      <div className="relative">
        <p
          className={`text-base sm:text-lg font-medium leading-relaxed ${
            isPartial ? 'text-secondary italic' : 'text-primary'
          }`}
        >
          &ldquo;{transcript}&rdquo;
        </p>
      </div>

      {/* Mobile note for confidence */}
      <div className="sm:hidden text-[10px] text-muted pt-1">
        Recognition confidence unavailable (Truthful backend policy)
      </div>
    </div>
  );
};
