import { CheckCircle, ChatCenteredText, Info } from '@phosphor-icons/react';
import { getLanguageDisplayLabel } from '../../types/api';

interface LiveTranscriptCardProps {
  transcript: string;
  isPartial: boolean;
  detectedLanguage: string;
  confidence: number | null;
  onSelectSamplePrompt?: (prompt: string) => void;
}

export interface SampleQuestion {
  text: string;
  lang: 'Hindi' | 'Hinglish' | 'English';
  code: 'hi' | 'hi-en' | 'en';
}

export const SAMPLE_QUESTIONS: SampleQuestion[] = [
  // Hindi (5)
  { text: 'मोह्स पैमाने पर सोने की कठोरता कितनी होती है?', lang: 'Hindi', code: 'hi' },
  { text: 'ऊर्ध्वाधर विभेदन क्या है?', lang: 'Hindi', code: 'hi' },
  { text: 'एस्टर-सी किससे बनाया जाता है', lang: 'Hindi', code: 'hi' },
  { text: 'क्या बराक ओबामा फिर से अमेरिकी राष्ट्रपति पद के लिए चुनाव लड़ सकते हैं?', lang: 'Hindi', code: 'hi' },
  { text: 'बी.आर.एल. किस देश की मुद्रा है', lang: 'Hindi', code: 'hi' },

  // Hinglish (5)
  { text: 'Sled pull karne ke liye kis type ke dogs use hote hain?', lang: 'Hinglish', code: 'hi-en' },
  { text: 'Xenotransplantation mein cells tissues ya organs kahan transfer hote hain?', lang: 'Hinglish', code: 'hi-en' },
  { text: 'Succulent plants ka meaning kya hai?', lang: 'Hinglish', code: 'hi-en' },
  { text: 'Hanker word ka meaning kya hai?', lang: 'Hinglish', code: 'hi-en' },
  { text: 'Biology mein blotting ka matlab kya hai?', lang: 'Hinglish', code: 'hi-en' },

  // English (5)
  { text: 'what is the net gain and loss', lang: 'English', code: 'en' },
  { text: 'which nhl team did jarmoir jagr play for', lang: 'English', code: 'en' },
  { text: 'whwen was the de lome letter published', lang: 'English', code: 'en' },
  { text: 'which judicial district is scot county', lang: 'English', code: 'en' },
  { text: 'what is d pathnathol', lang: 'English', code: 'en' },
];

export const LiveTranscriptCard: React.FC<LiveTranscriptCardProps> = ({
  transcript,
  isPartial,
  detectedLanguage,
  confidence,
  onSelectSamplePrompt,
}) => {
  if (!transcript) {
    return (
      <div className="refractive-glass-card refractive-glass-card-primary p-5 sm:p-6 space-y-4">
        <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-3">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-300 uppercase tracking-wider">
            <ChatCenteredText size={16} className="text-blue-400" />
            <span>Sample Verified Questions (15)</span>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            Click any question to ask
          </span>
        </div>

        {/* 3 Column Grid: Hindi | Hinglish | English */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Hindi Section */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-blue-300 px-1">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
              <span>Hindi (हिंदी)</span>
            </div>
            <div className="space-y-1.5">
              {SAMPLE_QUESTIONS.filter((q) => q.code === 'hi').map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSelectSamplePrompt?.(p.text)}
                  className="glass-btn w-full p-2.5 text-left cursor-pointer group"
                >
                  <p className="text-xs text-slate-200 group-hover:text-blue-300 leading-relaxed font-medium">
                    {p.text}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Hinglish Section */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-amber-300 px-1">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              <span>Hinglish (Code-Mixed)</span>
            </div>
            <div className="space-y-1.5">
              {SAMPLE_QUESTIONS.filter((q) => q.code === 'hi-en').map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSelectSamplePrompt?.(p.text)}
                  className="glass-btn w-full p-2.5 text-left cursor-pointer group"
                >
                  <p className="text-xs text-slate-200 group-hover:text-blue-300 leading-relaxed font-medium">
                    {p.text}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* English Section */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400 px-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span>English</span>
            </div>
            <div className="space-y-1.5">
              {SAMPLE_QUESTIONS.filter((q) => q.code === 'en').map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSelectSamplePrompt?.(p.text)}
                  className="glass-btn w-full p-2.5 text-left cursor-pointer group"
                >
                  <p className="text-xs text-slate-200 group-hover:text-blue-300 leading-relaxed font-medium">
                    {p.text}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      aria-live="polite"
      className="refractive-glass-card refractive-glass-card-primary p-5 sm:p-6 space-y-3 transition-all"
    >
      {/* Header with transcript status & detected language */}
      <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-3">
        <div className="flex items-center gap-2">
          {isPartial ? (
            <div className="flex items-center gap-2 text-xs font-bold text-blue-400">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-400" />
              </span>
              <span>Live Speech Transcript (Revisable Stream)</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400">
              <CheckCircle size={16} weight="fill" />
              <span>Final Question Transcript</span>
            </div>
          )}
        </div>

        {/* Language & Confidence Metadata */}
        <div className="flex items-center gap-2">
          {detectedLanguage && detectedLanguage !== 'unknown' && (
            <span className="px-2 py-0.5 rounded bg-black/30 border border-white/10 text-[10px] font-mono font-bold text-white uppercase">
              {getLanguageDisplayLabel(detectedLanguage)}
            </span>
          )}

          <div
            className="hidden sm:inline-flex items-center gap-1 text-[11px] text-slate-400"
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
            isPartial ? 'text-slate-300 italic' : 'text-white'
          }`}
        >
          &ldquo;{transcript}&rdquo;
        </p>
      </div>

      {/* Mobile note for confidence */}
      <div className="sm:hidden text-[10px] text-slate-500 pt-1">
        Recognition confidence unavailable (Truthful backend policy)
      </div>
    </div>
  );
};
